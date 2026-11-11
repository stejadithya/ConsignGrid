"""Inventory core: the ONLY code allowed to change stock.

Every change is recorded as append-only ledger entries and applied to the `stock_balances`
projection within the caller's database transaction. Balance rows are locked with
SELECT ... FOR UPDATE (in location/product order) before availability is checked, so
concurrent operations serialise on the rows they touch. See docs/INVENTORY_RULES.md.
"""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, InsufficientStockError, NotFoundError
from app.core.numbering import next_number
from app.modules.catalogue.models import Product
from app.modules.customers.models import (
    PHYSICAL_LOCATION_TYPES,
    SYSTEM_LOCATION_CODES,
    Location,
    LocationType,
)
from app.modules.inventory.models import (
    Bucket,
    InventoryEntry,
    InventoryTransaction,
    ReservationPurpose,
    ReservationStatus,
    StockBalance,
    StockReservation,
    TxnType,
)


@dataclass(frozen=True)
class Ref:
    """Business document that caused an inventory transaction."""

    type: str
    id: int | None = None
    number: str | None = None


def system_location(db: Session, loc_type: LocationType) -> Location:
    code = SYSTEM_LOCATION_CODES[loc_type]
    loc = db.execute(select(Location).where(Location.code == code)).scalar_one_or_none()
    if loc is None:  # pragma: no cover - created by migration
        raise RuntimeError(f"System location {code} missing; run migrations")
    return loc


def default_warehouse(db: Session) -> Location:
    loc = db.execute(
        select(Location).where(
            Location.type == LocationType.WAREHOUSE, Location.is_default_warehouse.is_(True),
            Location.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if loc is None:
        loc = db.execute(
            select(Location)
            .where(Location.type == LocationType.WAREHOUSE, Location.is_active.is_(True))
            .order_by(Location.id)
        ).scalars().first()
    if loc is None:
        raise BusinessRuleError("No active warehouse is configured")
    return loc


def get_balance(db: Session, location_id: int, product_id: int) -> StockBalance:
    """Unlocked read. Returns a transient zero balance when no row exists."""
    bal = db.get(StockBalance, (location_id, product_id))
    return bal or StockBalance(location_id=location_id, product_id=product_id, on_hand=0, reserved=0, blocked=0)


def lock_balances(db: Session, keys: list[tuple[int, int]]) -> dict[tuple[int, int], StockBalance]:
    """Create-if-missing and lock balance rows in deterministic order."""
    result: dict[tuple[int, int], StockBalance] = {}
    for location_id, product_id in sorted(set(keys)):
        db.execute(
            pg_insert(StockBalance)
            .values(location_id=location_id, product_id=product_id, on_hand=0, reserved=0, blocked=0)
            .on_conflict_do_nothing(index_elements=["location_id", "product_id"])
        )
        bal = db.execute(
            select(StockBalance)
            .where(StockBalance.location_id == location_id, StockBalance.product_id == product_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one()
        result[(location_id, product_id)] = bal
    return result


def _describe(db: Session, location: Location, product_id: int) -> str:
    product = db.get(Product, product_id)
    return f"{product.sku if product else product_id} at {location.code}"


def _check_qty(qty: int) -> None:
    if not isinstance(qty, int) or qty <= 0:
        raise BusinessRuleError("Quantity must be a positive whole number")


class Ledger:
    """Posts one inventory transaction. Create, call operations, then let the caller commit."""

    def __init__(
        self,
        db: Session,
        txn_type: TxnType,
        *,
        actor_id: int | None,
        ref: Ref | None = None,
        reason: str | None = None,
        notes: str | None = None,
        approved_by_id: int | None = None,
        reverses_transaction_id: int | None = None,
    ):
        self.db = db
        self.txn = InventoryTransaction(
            number=next_number(db, "TXN"),
            txn_type=txn_type,
            actor_user_id=actor_id,
            approved_by_user_id=approved_by_id,
            reference_type=ref.type if ref else None,
            reference_id=ref.id if ref else None,
            reference_number=ref.number if ref else None,
            reason=reason,
            notes=notes,
            reverses_transaction_id=reverses_transaction_id,
        )
        db.add(self.txn)
        db.flush()

    # -- internals -------------------------------------------------------------
    def _entry(self, location: Location, product_id: int, bucket: Bucket, qty: int, reservation_id: int | None = None):
        self.db.add(
            InventoryEntry(
                transaction_id=self.txn.id, product_id=product_id, location_id=location.id,
                bucket=bucket, quantity=qty, reservation_id=reservation_id,
            )
        )

    # -- operations ------------------------------------------------------------
    def move(
        self,
        product_id: int,
        source: Location,
        destination: Location,
        qty: int,
        *,
        reservation: StockReservation | None = None,
        from_blocked: bool = False,
    ) -> None:
        """Physically move qty from source to destination.

        Without a reservation, only *available* stock can leave a physical source. With a reservation,
        the reserved quantity is consumed. With from_blocked, blocked stock leaves (e.g. write-off).
        """
        _check_qty(qty)
        if source.id == destination.id:
            raise BusinessRuleError("Source and destination must differ")
        if not source.is_physical and not destination.is_physical:
            raise BusinessRuleError("A movement must involve at least one physical location")
        if reservation is not None and from_blocked:
            raise BusinessRuleError("Cannot move reserved and blocked stock in one operation")

        keys = [(loc.id, product_id) for loc in (source, destination) if loc.type in PHYSICAL_LOCATION_TYPES]
        balances = lock_balances(self.db, keys)

        if source.is_physical:
            src = balances[(source.id, product_id)]
            if reservation is not None:
                self._lock_reservation(reservation)
                if reservation.location_id != source.id or reservation.product_id != product_id:
                    raise BusinessRuleError("Reservation does not match the movement source/product")
                if reservation.open_qty < qty:
                    raise ConflictError(
                        f"Reservation has {reservation.open_qty} open, cannot consume {qty}"
                    )
                src.reserved -= qty
                reservation.consumed_qty += qty
                reservation.status = self._reservation_status(reservation)
                self._entry(source, product_id, Bucket.RESERVED, -qty, reservation.id)
            elif from_blocked:
                if src.blocked < qty:
                    raise InsufficientStockError(
                        f"Only {src.blocked} blocked for {_describe(self.db, source, product_id)}"
                    )
                src.blocked -= qty
                self._entry(source, product_id, Bucket.BLOCKED, -qty)
            elif src.available < qty:
                raise InsufficientStockError(
                    f"Only {src.available} available for {_describe(self.db, source, product_id)}; requested {qty}"
                )
            src.on_hand -= qty
        self._entry(source, product_id, Bucket.ON_HAND, -qty)

        if destination.is_physical:
            balances[(destination.id, product_id)].on_hand += qty
        self._entry(destination, product_id, Bucket.ON_HAND, qty)
        self.db.flush()

    def reserve(
        self,
        location: Location,
        product_id: int,
        qty: int,
        purpose: ReservationPurpose,
        ref: Ref | None = None,
    ) -> StockReservation:
        _check_qty(qty)
        if not location.is_physical or location.type == LocationType.TRANSIT:
            raise BusinessRuleError("Stock can only be reserved at a warehouse or consignment location")
        bal = lock_balances(self.db, [(location.id, product_id)])[(location.id, product_id)]
        if bal.available < qty:
            raise InsufficientStockError(
                f"Only {bal.available} available for {_describe(self.db, location, product_id)}; requested {qty}"
            )
        res = StockReservation(
            location_id=location.id, product_id=product_id, quantity=qty, purpose=purpose,
            reference_type=ref.type if ref else None, reference_id=ref.id if ref else None,
            created_by_user_id=self.txn.actor_user_id,
        )
        self.db.add(res)
        self.db.flush()
        bal.reserved += qty
        self._entry(location, product_id, Bucket.RESERVED, qty, res.id)
        self.db.flush()
        return res

    def release(self, reservation: StockReservation, qty: int | None = None) -> int:
        """Release (part of) a reservation. Returns the quantity released."""
        location = self.db.get(Location, reservation.location_id)
        bal = lock_balances(self.db, [(reservation.location_id, reservation.product_id)])[
            (reservation.location_id, reservation.product_id)
        ]
        self._lock_reservation(reservation)
        qty = reservation.open_qty if qty is None else qty
        if qty <= 0:
            return 0
        if qty > reservation.open_qty:
            raise ConflictError(f"Reservation has only {reservation.open_qty} open")
        bal.reserved -= qty
        reservation.released_qty += qty
        reservation.status = self._reservation_status(reservation)
        self._entry(location, reservation.product_id, Bucket.RESERVED, -qty, reservation.id)
        self.db.flush()
        return qty

    def block(self, location: Location, product_id: int, qty: int) -> None:
        _check_qty(qty)
        bal = lock_balances(self.db, [(location.id, product_id)])[(location.id, product_id)]
        if bal.available < qty:
            raise InsufficientStockError(
                f"Only {bal.available} available to block for {_describe(self.db, location, product_id)}"
            )
        bal.blocked += qty
        self._entry(location, product_id, Bucket.BLOCKED, qty)
        self.db.flush()

    def unblock(self, location: Location, product_id: int, qty: int) -> None:
        _check_qty(qty)
        bal = lock_balances(self.db, [(location.id, product_id)])[(location.id, product_id)]
        if bal.blocked < qty:
            raise InsufficientStockError(
                f"Only {bal.blocked} blocked for {_describe(self.db, location, product_id)}"
            )
        bal.blocked -= qty
        self._entry(location, product_id, Bucket.BLOCKED, -qty)
        self.db.flush()

    # -- helpers ---------------------------------------------------------------
    def _lock_reservation(self, reservation: StockReservation) -> None:
        self.db.execute(
            select(StockReservation)
            .where(StockReservation.id == reservation.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one()

    @staticmethod
    def _reservation_status(r: StockReservation) -> ReservationStatus:
        if r.open_qty > 0:
            return ReservationStatus.ACTIVE
        if r.released_qty == 0:
            return ReservationStatus.CONSUMED
        if r.consumed_qty == 0:
            return ReservationStatus.RELEASED
        return ReservationStatus.CLOSED


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


@dataclass
class ReconciliationDifference:
    location_id: int
    product_id: int
    bucket: str
    ledger_qty: int
    balance_qty: int


def reconcile(db: Session, location_id: int | None = None) -> list[ReconciliationDifference]:
    """Rebuild balances of physical locations from ledger entries and compare with the projection."""
    q = (
        select(InventoryEntry.location_id, InventoryEntry.product_id, InventoryEntry.bucket,
               func.sum(InventoryEntry.quantity))
        .join(Location, Location.id == InventoryEntry.location_id)
        .where(Location.type.in_([t.value for t in PHYSICAL_LOCATION_TYPES]))
        .group_by(InventoryEntry.location_id, InventoryEntry.product_id, InventoryEntry.bucket)
    )
    bq = select(StockBalance)
    if location_id is not None:
        q = q.where(InventoryEntry.location_id == location_id)
        bq = bq.where(StockBalance.location_id == location_id)

    ledger: dict[tuple[int, int], dict[str, int]] = defaultdict(lambda: {b.value: 0 for b in Bucket})
    for loc_id, prod_id, bucket, total in db.execute(q):
        ledger[(loc_id, prod_id)][Bucket(bucket).value] = int(total)

    projected: dict[tuple[int, int], dict[str, int]] = {}
    for bal in db.execute(bq).scalars():
        projected[(bal.location_id, bal.product_id)] = {
            Bucket.ON_HAND.value: bal.on_hand, Bucket.RESERVED.value: bal.reserved, Bucket.BLOCKED.value: bal.blocked,
        }

    diffs: list[ReconciliationDifference] = []
    zero = {b.value: 0 for b in Bucket}
    for key in sorted(set(ledger) | set(projected)):
        lv, pv = ledger.get(key, zero), projected.get(key, zero)
        for b in Bucket:
            if lv[b.value] != pv[b.value]:
                diffs.append(ReconciliationDifference(key[0], key[1], b.value, lv[b.value], pv[b.value]))
    return diffs


def unbalanced_transactions(db: Session) -> list[int]:
    """Transactions whose ON_HAND entries do not sum to zero (should always be empty)."""
    rows = db.execute(
        select(InventoryEntry.transaction_id)
        .where(InventoryEntry.bucket == Bucket.ON_HAND)
        .group_by(InventoryEntry.transaction_id)
        .having(func.sum(InventoryEntry.quantity) != 0)
    ).scalars()
    return list(rows)


def get_location(db: Session, location_id: int) -> Location:
    loc = db.get(Location, location_id)
    if loc is None:
        raise NotFoundError("Location not found")
    return loc
