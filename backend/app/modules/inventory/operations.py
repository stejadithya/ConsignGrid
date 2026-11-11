"""User-facing stock operations (opening balances, adjustments, blocking) and stock queries."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import BusinessRuleError, NotFoundError
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product
from app.modules.customers.models import (
    ConsignmentAgreement,
    Location,
    LocationType,
    Reseller,
)
from app.modules.identity.models import User
from app.modules.identity.scoping import scoped_reseller_id
from app.modules.inventory.models import InventoryEntry, InventoryTransaction, StockBalance, TxnType
from app.modules.inventory.schemas import (
    AdjustmentIn,
    AvailabilityRow,
    BalanceOut,
    OpeningBalanceIn,
    StockStateChangeIn,
)
from app.modules.inventory.service import Ledger, Ref, get_location, system_location

STOCK_HOLDING = (LocationType.WAREHOUSE, LocationType.CONSIGNMENT)


def _stock_location(db: Session, location_id: int) -> Location:
    loc = get_location(db, location_id)
    if loc.type not in STOCK_HOLDING:
        raise BusinessRuleError("Operation allowed only at a warehouse or consignment location")
    if not loc.is_active:
        raise BusinessRuleError(f"Location {loc.code} is inactive")
    return loc


def _product(db: Session, product_id: int) -> Product:
    p = db.get(Product, product_id)
    if p is None:
        raise NotFoundError("Product not found")
    return p


def post_opening_balance(db: Session, actor: User, data: OpeningBalanceIn,
                         reason: str = "Opening balance") -> InventoryTransaction:
    loc = _stock_location(db, data.location_id)
    opening = system_location(db, LocationType.OPENING)
    ledger = Ledger(db, TxnType.OPENING_BALANCE, actor_id=actor.id, approved_by_id=actor.id,
                    ref=Ref("location", loc.id, loc.code), notes=data.notes, reason=reason)
    for line in data.lines:
        _product(db, line.product_id)
        ledger.move(line.product_id, opening, loc, line.quantity)
    record_audit(db, actor_id=actor.id, action="inventory.opening_balance", entity_type="inventory_transaction",
                 entity_id=ledger.txn.id, reseller_id=loc.reseller_id,
                 summary=f"Opening balance {ledger.txn.number} at {loc.code}: {sum(ln.quantity for ln in data.lines)} units")
    return ledger.txn


def post_adjustment(db: Session, actor: User, data: AdjustmentIn) -> InventoryTransaction:
    loc = _stock_location(db, data.location_id)
    product = _product(db, data.product_id)
    adj = system_location(db, LocationType.ADJUSTMENT)
    ledger = Ledger(db, TxnType.ADJUSTMENT, actor_id=actor.id, approved_by_id=actor.id,
                    ref=Ref("location", loc.id, loc.code), reason=data.reason)
    if data.quantity_delta > 0:
        ledger.move(product.id, adj, loc, data.quantity_delta)
    else:
        ledger.move(product.id, loc, adj, -data.quantity_delta)
    record_audit(db, actor_id=actor.id, action="inventory.adjust", entity_type="inventory_transaction",
                 entity_id=ledger.txn.id, reseller_id=loc.reseller_id,
                 summary=f"Adjusted {product.sku} at {loc.code} by {data.quantity_delta:+d}: {data.reason}")
    return ledger.txn


def change_block(db: Session, actor: User, data: StockStateChangeIn, *, block: bool) -> InventoryTransaction:
    loc = _stock_location(db, data.location_id)
    product = _product(db, data.product_id)
    ledger = Ledger(db, TxnType.BLOCK if block else TxnType.UNBLOCK, actor_id=actor.id,
                    ref=Ref("location", loc.id, loc.code), reason=data.reason)
    if block:
        ledger.block(loc, product.id, data.quantity)
    else:
        ledger.unblock(loc, product.id, data.quantity)
    verb = "Blocked" if block else "Unblocked"
    record_audit(db, actor_id=actor.id, action=f"inventory.{'block' if block else 'unblock'}",
                 entity_type="inventory_transaction", entity_id=ledger.txn.id, reseller_id=loc.reseller_id,
                 summary=f"{verb} {data.quantity} × {product.sku} at {loc.code}: {data.reason}")
    return ledger.txn


def write_off_blocked(db: Session, actor: User, data: StockStateChangeIn) -> InventoryTransaction:
    loc = _stock_location(db, data.location_id)
    product = _product(db, data.product_id)
    scrap = system_location(db, LocationType.SCRAP)
    ledger = Ledger(db, TxnType.WRITE_OFF, actor_id=actor.id, approved_by_id=actor.id,
                    ref=Ref("location", loc.id, loc.code), reason=data.reason)
    ledger.move(product.id, loc, scrap, data.quantity, from_blocked=True)
    record_audit(db, actor_id=actor.id, action="inventory.write_off", entity_type="inventory_transaction",
                 entity_id=ledger.txn.id, reseller_id=loc.reseller_id,
                 summary=f"Wrote off {data.quantity} blocked × {product.sku} at {loc.code}: {data.reason}")
    return ledger.txn


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def list_balances(
    db: Session, user: User, *, location_id: int | None = None, product_id: int | None = None,
    location_type: LocationType | None = None, reseller_id: int | None = None, include_zero: bool = False,
) -> list[BalanceOut]:
    stmt = (
        select(StockBalance, Location, Product)
        .join(Location, Location.id == StockBalance.location_id)
        .join(Product, Product.id == StockBalance.product_id)
    )
    restricted = scoped_reseller_id(user)
    if restricted is not None:
        stmt = stmt.where(Location.reseller_id == restricted)
    if location_id is not None:
        stmt = stmt.where(StockBalance.location_id == location_id)
    if product_id is not None:
        stmt = stmt.where(StockBalance.product_id == product_id)
    if location_type is not None:
        stmt = stmt.where(Location.type == location_type)
    if reseller_id is not None:
        stmt = stmt.where(Location.reseller_id == reseller_id)
    if not include_zero:
        stmt = stmt.where(StockBalance.on_hand != 0)
    rows = db.execute(stmt.order_by(Location.code, Product.sku)).tuples()
    return [
        BalanceOut(
            location_id=loc.id, location_code=loc.code, location_name=loc.name, location_type=loc.type,
            reseller_id=loc.reseller_id, product_id=p.id, sku=p.sku, product_name=p.display_name,
            on_hand=b.on_hand, reserved=b.reserved, blocked=b.blocked, available=b.available,
        )
        for b, loc, p in rows
    ]


def availability_by_product(db: Session, product_id: int) -> list[AvailabilityRow]:
    """Stock of one exact SKU at every warehouse and consignment location (dealership staff only)."""
    _product(db, product_id)
    rows = db.execute(
        select(StockBalance, Location, Reseller, ConsignmentAgreement.transfer_consent)
        .join(Location, Location.id == StockBalance.location_id)
        .outerjoin(Reseller, Reseller.id == Location.reseller_id)
        .outerjoin(ConsignmentAgreement, ConsignmentAgreement.reseller_id == Reseller.id)
        .where(StockBalance.product_id == product_id,
               Location.type.in_([LocationType.WAREHOUSE.value, LocationType.CONSIGNMENT.value]),
               StockBalance.on_hand > 0)
        .order_by(Location.type.desc(), Location.code)
    ).tuples()
    return [
        AvailabilityRow(
            location_id=loc.id, location_code=loc.code, location_name=loc.name, location_type=loc.type,
            reseller_id=loc.reseller_id, reseller_name=r.business_name if r else None,
            reseller_status=r.status if r else None, transfer_consent=consent,
            on_hand=b.on_hand, reserved=b.reserved, blocked=b.blocked, available=b.available,
        )
        for b, loc, r, consent in rows
    ]


def list_transactions(
    db: Session, user: User, *, location_id: int | None = None, product_id: int | None = None,
    reference_type: str | None = None, reference_id: int | None = None, txn_type: TxnType | None = None,
    limit: int = 100, offset: int = 0, number: str | None = None,
) -> list[InventoryTransaction]:
    stmt = select(InventoryTransaction).options(selectinload(InventoryTransaction.entries))
    if number:   # one movement by its number (opened from the search box)
        stmt = stmt.where(InventoryTransaction.number == number.strip().upper())
    restricted = scoped_reseller_id(user)
    entry_filter = select(InventoryEntry.transaction_id)
    filtered = False
    if restricted is not None:
        entry_filter = entry_filter.join(Location, Location.id == InventoryEntry.location_id).where(
            Location.reseller_id == restricted
        )
        filtered = True
    if location_id is not None:
        entry_filter = entry_filter.where(InventoryEntry.location_id == location_id)
        filtered = True
    if product_id is not None:
        entry_filter = entry_filter.where(InventoryEntry.product_id == product_id)
        filtered = True
    if filtered:
        stmt = stmt.where(InventoryTransaction.id.in_(entry_filter))
    if reference_type:
        stmt = stmt.where(InventoryTransaction.reference_type == reference_type)
    if reference_id is not None:
        stmt = stmt.where(InventoryTransaction.reference_id == reference_id)
    if txn_type is not None:
        stmt = stmt.where(InventoryTransaction.txn_type == txn_type)
    stmt = stmt.order_by(InventoryTransaction.id.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars())
