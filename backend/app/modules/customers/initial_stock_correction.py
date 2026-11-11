"""Correct a dealer's initial stock that was entered wrongly (Relationship Manager and Administrator only).

The original entry is never edited or deleted. A correction is a new ledger transaction (INITIAL_STOCK_CORRECTION)
that points at the entry it corrects (reverses_transaction_id) and moves only the difference: tyres taken out go
back to the opening system location (they were never really there), tyres added come from it. So the stock
figures still reconcile and every correction can be traced: who, when, before → after per tyre, and why.

Rules:
- Only stock still free at the shop can be taken out: tyres sold, reserved or blocked are not a typing mistake.
- Corrections are allowed until the first stock check at that shop, and for INITIAL_STOCK_CORRECTION_DAYS (30)
  after the entry. After that, differences go through a stock check (its find window and invoicing).
- A correction is never invoiced and raises no replacement.
- Administrators and Finance Managers are told about every correction.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.industry import vocab
from app.core.permissions import Role
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product
from app.modules.customers.models import Location, LocationType, Reseller
from app.modules.identity.models import User
from app.modules.inventory.models import Bucket, InventoryEntry, InventoryTransaction, TxnType
from app.modules.inventory.service import Ledger, Ref, get_balance, system_location
from app.modules.notifications.service import notify_users, staff_in_roles
from app.modules.stocktakes.models import Stocktake, StocktakeStatus

ACTION = "inventory.initial_stock_correct"
_NOT_A_COUNT = (StocktakeStatus.DRAFT, StocktakeStatus.CANCELLED)


@dataclass
class EntryLine:
    product_id: int
    sku: str
    name: str
    recorded: int        # as first entered
    current: int         # after corrections
    free_now: int        # free at the shop today (on hand, not reserved or blocked)


@dataclass
class Change:
    product_id: int
    sku: str
    name: str
    before: int
    after: int


@dataclass
class Correction:
    transaction_id: int
    transaction_number: str
    corrected_at: datetime
    corrected_by: str | None
    reason: str
    changes: list[Change] = field(default_factory=list)


@dataclass
class Entry:
    transaction_id: int
    transaction_number: str
    recorded_at: datetime
    recorded_by: str | None
    location_id: int
    location_code: str
    location_name: str
    lines: list[EntryLine]
    corrections: list[Correction]
    can_correct: bool
    locked_reason: str | None
    correctable_until: datetime | None


def _dealer_locations(db: Session, reseller_id: int) -> dict[int, Location]:
    if db.get(Reseller, reseller_id) is None:
        raise NotFoundError(f"{vocab.Partner} not found")
    return {loc.id: loc for loc in db.execute(select(Location).where(
        Location.reseller_id == reseller_id, Location.type == LocationType.CONSIGNMENT)).scalars()}


def _on_hand_by_product(db: Session, txn_ids: list[int], location_id: int) -> dict[int, dict[int, int]]:
    """{transaction id: {product id: on-hand change at the shop}}."""
    out: dict[int, dict[int, int]] = {t: {} for t in txn_ids}
    if not txn_ids:
        return out
    rows = db.execute(select(InventoryEntry.transaction_id, InventoryEntry.product_id, InventoryEntry.quantity).where(
        InventoryEntry.transaction_id.in_(txn_ids), InventoryEntry.location_id == location_id,
        InventoryEntry.bucket == Bucket.ON_HAND)).all()
    for tid, pid, q in rows:
        out[tid][pid] = out[tid].get(pid, 0) + q
    return out


def _lock(db: Session, txn: InventoryTransaction, location_id: int) -> tuple[str | None, datetime]:
    """Why this entry can no longer be corrected (None = it can), and until when it could be."""
    until = txn.occurred_at + timedelta(days=get_settings().initial_stock_correction_days)
    counted = db.execute(select(Stocktake.number).where(
        Stocktake.location_id == location_id, Stocktake.status.not_in(_NOT_A_COUNT))
        .order_by(Stocktake.id).limit(1)).scalar_one_or_none()
    if counted:
        return (f"A stock check ({counted}) has been done at this {vocab.site} since. "
                "Use a stock check for any differences."), until
    if datetime.now(UTC) > until:
        return (f"Initial stock can be corrected for {get_settings().initial_stock_correction_days} days. "
                "Use a stock check for any differences."), until
    return None, until


def entries(db: Session, reseller_id: int) -> list[Entry]:
    """The dealer's initial stock entries, each with its corrections, oldest first."""
    locs = _dealer_locations(db, reseller_id)
    if not locs:
        return []
    originals = list(db.execute(select(InventoryTransaction).join(
        InventoryEntry, InventoryEntry.transaction_id == InventoryTransaction.id).where(
        InventoryTransaction.txn_type == TxnType.OPENING_BALANCE, InventoryEntry.location_id.in_(list(locs)))
        .distinct().order_by(InventoryTransaction.occurred_at, InventoryTransaction.id)).scalars())
    if not originals:
        return []
    fixes = list(db.execute(select(InventoryTransaction).where(
        InventoryTransaction.txn_type == TxnType.INITIAL_STOCK_CORRECTION,
        InventoryTransaction.reverses_transaction_id.in_([t.id for t in originals]))
        .order_by(InventoryTransaction.occurred_at, InventoryTransaction.id)).scalars())
    user_ids = {t.actor_user_id for t in originals + fixes if t.actor_user_id}
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids))).all()) if user_ids else {}

    out = []
    for txn in originals:
        loc_id = db.execute(select(InventoryEntry.location_id).where(
            InventoryEntry.transaction_id == txn.id, InventoryEntry.location_id.in_(list(locs))).limit(1)).scalar_one()
        mine = [f for f in fixes if f.reverses_transaction_id == txn.id]
        moves = _on_hand_by_product(db, [txn.id] + [f.id for f in mine], loc_id)
        recorded = moves[txn.id]
        running = dict(recorded)
        pids = set(recorded) | {pid for f in mine for pid in moves[f.id]}
        products = {p.id: p for p in db.execute(select(Product).where(Product.id.in_(pids))).scalars()}
        corrections = []
        for f in mine:
            changes = []
            for pid, delta in sorted(moves[f.id].items(), key=lambda kv: products[kv[0]].sku):
                before = running.get(pid, 0)
                running[pid] = before + delta
                changes.append(Change(pid, products[pid].sku, products[pid].display_name, before, before + delta))
            corrections.append(Correction(f.id, f.number, f.occurred_at, names.get(f.actor_user_id), f.reason or "", changes))
        lines = sorted((EntryLine(pid, products[pid].sku, products[pid].display_name, recorded.get(pid, 0),
                                  running.get(pid, 0), get_balance(db, loc_id, pid).available)
                        for pid in pids), key=lambda ln: ln.sku)
        locked, until = _lock(db, txn, loc_id)
        loc = locs[loc_id]
        out.append(Entry(txn.id, txn.number, txn.occurred_at, names.get(txn.actor_user_id), loc.id, loc.code, loc.name,
                         lines, corrections, locked is None, locked, until))
    return out


def correct(db: Session, actor: User, reseller_id: int, transaction_id: int,
            lines: list[tuple[int, int]], reason: str) -> Correction:
    """Set each listed tyre's quantity on the entry to the correct figure. Unlisted tyres stay as they are."""
    entry = next((e for e in entries(db, reseller_id) if e.transaction_id == transaction_id), None)
    if entry is None:
        raise NotFoundError("Initial stock entry not found")
    if not entry.can_correct:
        raise BusinessRuleError(entry.locked_reason or "This initial stock can no longer be corrected")
    reason = reason.strip()
    if len(reason) < 5:
        raise BusinessRuleError("Say what was wrong (at least 5 characters)")
    current = {ln.product_id: ln for ln in entry.lines}
    wanted: dict[int, int] = {}
    for pid, qty in lines:
        if pid in wanted:
            raise BusinessRuleError(f"Each {vocab.item} can appear only once")
        wanted[pid] = qty
    products = {p.id: p for p in db.execute(select(Product).where(Product.id.in_(list(wanted)))).scalars()}
    deltas: list[tuple[Product, int, int]] = []          # (product, before, after)
    for pid, after in wanted.items():
        p = products.get(pid)
        if p is None:
            raise NotFoundError("Product not found")
        if pid not in current and not p.is_active:
            raise BusinessRuleError(f"{p.sku} is not an active {vocab.item}")
        before = current[pid].current if pid in current else 0
        if after == before:
            continue
        if after < before:
            free = current[pid].free_now
            if before - after > free:
                raise BusinessRuleError(
                    f"{p.display_name} ({p.sku}): only {free} of the {before} are still free at the {vocab.site}, so it can go "
                    f"down to {before - free} at the least. Sold, reserved or blocked {vocab.items} can't be corrected away.")
        deltas.append((p, before, after))
    if not deltas:
        raise BusinessRuleError("Nothing to change: the quantities are the same as now")

    loc = db.get(Location, entry.location_id)
    opening = system_location(db, LocationType.OPENING)
    ledger = Ledger(db, TxnType.INITIAL_STOCK_CORRECTION, actor_id=actor.id, approved_by_id=actor.id,
                    ref=Ref("location", loc.id, loc.code), reason=reason, reverses_transaction_id=entry.transaction_id)
    for p, before, after in deltas:
        if after > before:
            ledger.move(p.id, opening, loc, after - before)
        else:
            ledger.move(p.id, loc, opening, before - after)

    reseller = db.get(Reseller, reseller_id)
    changes = [Change(p.id, p.sku, p.display_name, b, a) for p, b, a in sorted(deltas, key=lambda d: d[0].sku)]
    words = "; ".join(f"{c.sku} {c.before} → {c.after}" for c in changes)
    record_audit(db, actor_id=actor.id, action=ACTION, entity_type="inventory_transaction", entity_id=ledger.txn.id,
                 reseller_id=reseller_id,
                 summary=f"Corrected initial stock {entry.transaction_number} at {loc.code}: {words}. Reason: {reason}",
                 details={"corrects_transaction": entry.transaction_number, "location": loc.code, "reason": reason,
                          "changes": [{"sku": c.sku, "before": c.before, "after": c.after} for c in changes]})
    notify_users(db, staff_in_roles(db, Role.ADMINISTRATOR, Role.FINANCE_MANAGER),
                 f"Initial stock corrected: {reseller.business_name}",
                 f"{actor.full_name} corrected {entry.transaction_number} at {loc.code}: {words}. Reason: {reason}",
                 link=f"/resellers/{reseller_id}", entity_type="reseller", entity_id=reseller_id, exclude=actor.id)
    return Correction(ledger.txn.id, ledger.txn.number, ledger.txn.occurred_at, actor.full_name, reason, changes)
