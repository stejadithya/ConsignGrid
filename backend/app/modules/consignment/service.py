from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import flush_or_conflict
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.industry import vocab
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product
from app.modules.consignment.models import AllocationChange, ConsignmentAllocation
from app.modules.consignment.schemas import AllocationIn
from app.modules.customers.models import ConsignmentAgreement, Location, LocationType
from app.modules.identity.models import User
from app.modules.identity.scoping import ensure_reseller_access


def lock_allocation(db: Session, location_id: int, product_id: int) -> ConsignmentAllocation | None:
    """Lock the allocation row: serialises demand creation for the same shortfall."""
    return db.execute(
        select(ConsignmentAllocation)
        .where(ConsignmentAllocation.location_id == location_id, ConsignmentAllocation.product_id == product_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def set_allocation(db: Session, actor: User, data: AllocationIn) -> ConsignmentAllocation:
    location = db.get(Location, data.location_id)
    if location is None or location.type != LocationType.CONSIGNMENT:
        raise BusinessRuleError(f"Allocations can only be set for {vocab.partner} consignment locations")
    product = db.get(Product, data.product_id)
    if product is None:
        raise NotFoundError("Product not found")
    if not product.is_active and data.target_qty > 0:
        raise BusinessRuleError(f"{product.sku} is inactive; its target can only be set to 0")

    alloc = lock_allocation(db, location.id, product.id)
    if data.auto_replenish is None:
        agreement = db.execute(
            select(ConsignmentAgreement).where(ConsignmentAgreement.reseller_id == location.reseller_id)
        ).scalar_one_or_none()
        default_auto = agreement.auto_replenish_default if agreement else True
        auto = alloc.auto_replenish if alloc else default_auto
    else:
        auto = data.auto_replenish

    old_target, old_auto = (alloc.target_qty, alloc.auto_replenish) if alloc else (None, None)
    if alloc is None:
        alloc = ConsignmentAllocation(location_id=location.id, product_id=product.id, target_qty=data.target_qty)
        flush_or_conflict(db, alloc, "The allocation was changed concurrently; please retry")
    alloc.target_qty = data.target_qty
    alloc.min_qty = data.min_qty
    alloc.max_qty = data.max_qty
    alloc.auto_replenish = auto
    alloc.is_active = True
    db.flush()
    db.add(AllocationChange(
        allocation_id=alloc.id, old_target_qty=old_target, new_target_qty=data.target_qty,
        old_auto_replenish=old_auto, new_auto_replenish=auto, reason=data.reason, changed_by_user_id=actor.id,
    ))
    record_audit(db, actor_id=actor.id, action="allocation.set", entity_type="consignment_allocation",
                 entity_id=alloc.id, reseller_id=location.reseller_id,
                 summary=f"{location.code} {product.sku}: target {old_target} → {data.target_qty} ({data.reason})")
    db.flush()
    return alloc


def list_allocations(db: Session, user: User, *, reseller_id: int | None = None,
                     location_id: int | None = None) -> list[ConsignmentAllocation]:
    stmt = select(ConsignmentAllocation).join(Location, Location.id == ConsignmentAllocation.location_id)
    if user.is_reseller_user:
        stmt = stmt.where(Location.reseller_id == user.reseller_id)
    if reseller_id is not None:
        stmt = stmt.where(Location.reseller_id == reseller_id)
    if location_id is not None:
        stmt = stmt.where(ConsignmentAllocation.location_id == location_id)
    return list(db.execute(stmt.order_by(Location.code, ConsignmentAllocation.product_id)).scalars())


def allocation_history(db: Session, user: User, allocation_id: int) -> list[AllocationChange]:
    alloc = db.get(ConsignmentAllocation, allocation_id)
    if alloc is None:
        raise NotFoundError("Allocation not found")
    loc = db.get(Location, alloc.location_id)
    ensure_reseller_access(user, loc.reseller_id, "Allocation")
    return list(db.execute(
        select(AllocationChange).where(AllocationChange.allocation_id == allocation_id)
        .order_by(AllocationChange.changed_at.desc(), AllocationChange.id.desc())
    ).scalars())


def positions(db: Session, user: User, *, reseller_id: int | None = None, location_id: int | None = None):
    """Target vs actual for each allocated (or stocked) SKU at consignment locations."""
    from app.modules.consignment.schemas import AllocationPosition
    from app.modules.inventory.models import StockBalance
    from app.modules.replenishment.service import coverage

    loc_stmt = select(Location).where(Location.type == LocationType.CONSIGNMENT)
    if user.is_reseller_user:
        loc_stmt = loc_stmt.where(Location.reseller_id == user.reseller_id)
    if reseller_id is not None:
        loc_stmt = loc_stmt.where(Location.reseller_id == reseller_id)
    if location_id is not None:
        loc_stmt = loc_stmt.where(Location.id == location_id)
    locs = {loc.id: loc for loc in db.execute(loc_stmt).scalars()}
    if not locs:
        return []
    allocs = {(a.location_id, a.product_id): a for a in db.execute(
        select(ConsignmentAllocation).where(ConsignmentAllocation.location_id.in_(locs))).scalars()}
    stocked = {(b.location_id, b.product_id): b for b in db.execute(
        select(StockBalance).where(StockBalance.location_id.in_(locs), StockBalance.on_hand > 0)).scalars()}
    keys = sorted(set(allocs) | set(stocked))
    products = {p.id: p for p in db.execute(select(Product).where(Product.id.in_({k[1] for k in keys} or {-1}))).scalars()}
    out = []
    for loc_id, prod_id in keys:
        a = allocs.get((loc_id, prod_id))
        cov = coverage(db, loc_id, prod_id, a)
        b = stocked.get((loc_id, prod_id))
        p = products[prod_id]
        out.append(AllocationPosition(
            allocation_id=a.id if a else None, location_id=loc_id, location_code=locs[loc_id].code,
            reseller_id=locs[loc_id].reseller_id, product_id=prod_id, sku=p.sku, product_name=p.display_name,
            target_qty=a.target_qty if a and a.is_active else 0, auto_replenish=bool(a and a.auto_replenish),
            on_hand=cov.on_hand, reserved=b.reserved if b else 0, blocked=b.blocked if b else 0,
            available=b.available if b else 0, open_replenishment=cov.open_outstanding,
            replenishment_in_transit=cov.in_transit_replenishment, transfers_inbound=cov.inbound_transfers,
            remaining_unmet=cov.shortfall,
        ))
    out.sort(key=lambda x: (x.location_code, x.sku))
    return out
