"""Replenishment demand, warehouse allocation, dispatch and delivery. Never creates invoices.

See docs/INVENTORY_RULES.md §5 for the quantity model and shortfall rules.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.industry import vocab
from app.core.messages import KIND_REJECTION
from app.core.numbering import next_number
from app.core.permissions import P, Role, role_has
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product
from app.modules.consignment.models import ConsignmentAllocation
from app.modules.consignment.service import lock_allocation
from app.modules.customers.models import Location, LocationType, Reseller, ResellerStatus
from app.modules.identity.models import User
from app.modules.identity.scoping import ensure_reseller_access
from app.modules.inventory.models import InventoryEntry, ReservationPurpose, StockReservation, TxnType
from app.modules.inventory.service import Ledger, Ref, default_warehouse, get_balance, system_location
from app.modules.notifications.service import notify_users, reseller_users, staff_in_roles, staff_with
from app.modules.proofs import service as proofs
from app.modules.purchasing.models import PurchaseOrderLine
from app.modules.replenishment.models import (
    OPEN_STATUSES,
    PRIORITY_RANK,
    AllocationStatus,
    Delivery,
    DeliveryLine,
    DeliveryStatus,
    Priority,
    ReplenishmentAllocation,
    ReplenishmentEvent,
    ReplenishmentReason,
    ReplenishmentRequest,
)
from app.modules.transfers.models import Transfer, TransferStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def lock_request(db: Session, request_id: int) -> ReplenishmentRequest:
    req = db.execute(
        select(ReplenishmentRequest)
        .where(ReplenishmentRequest.id == request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if req is None:
        raise NotFoundError("Replenishment request not found")
    return req


def _event(db: Session, req: ReplenishmentRequest, event_type: str, qty: int | None, actor_id: int | None,
           ref: Ref | None = None, reason: str | None = None) -> None:
    db.add(ReplenishmentEvent(
        request_id=req.id, event_type=event_type, quantity=qty, actor_user_id=actor_id,
        reference_type=ref.type if ref else None, reference_id=ref.id if ref else None,
        reference_number=ref.number if ref else None, reason=reason,
    ))


def _refresh(req: ReplenishmentRequest) -> None:
    req.status = req.derive_status()
    if req.status not in OPEN_STATUSES and req.closed_at is None:
        req.closed_at = _now()


def _sync_stock_requests(db: Session, request_ids: list[int]) -> None:
    """Keep consignment stock request statuses in step with the replenishment requests they created."""
    from app.modules.stock_requests.service import sync_for_replenishment  # stock requests build on this module

    sync_for_replenishment(db, request_ids)


def _require(user: User, perm: P) -> None:
    if not role_has(user.role, perm):
        raise PermissionDeniedError(f"Missing permission: {perm.value}")


# ---------------------------------------------------------------------------
# Coverage / shortfall
# ---------------------------------------------------------------------------


@dataclass
class Coverage:
    target: int | None
    auto_replenish: bool
    on_hand: int
    open_outstanding: int
    in_transit_replenishment: int
    inbound_transfers: int

    @property
    def covered(self) -> int:
        return self.on_hand + self.open_outstanding + self.inbound_transfers

    @property
    def shortfall(self) -> int:
        return max(0, (self.target or 0) - self.covered)


def open_outstanding(db: Session, location_id: int, product_id: int) -> tuple[int, int]:
    """(outstanding, in_transit) across open requests for a location + product."""
    row = db.execute(
        select(
            func.coalesce(func.sum(ReplenishmentRequest.qty_required - ReplenishmentRequest.qty_delivered
                                   - ReplenishmentRequest.qty_cancelled), 0),
            func.coalesce(func.sum(ReplenishmentRequest.qty_in_transit), 0),
        ).where(
            ReplenishmentRequest.location_id == location_id, ReplenishmentRequest.product_id == product_id,
            ReplenishmentRequest.status.in_([s.value for s in OPEN_STATUSES]),
        )
    ).one()
    return int(row[0]), int(row[1])


def inbound_transfers(db: Session, location_id: int, product_id: int) -> int:
    """Open inbound transfer quantity not already represented by a destination request."""
    rows = db.execute(
        select(Transfer).where(
            Transfer.destination_location_id == location_id, Transfer.product_id == product_id,
            Transfer.destination_request_id.is_(None),
            Transfer.status.in_([TransferStatus.APPROVED.value, TransferStatus.IN_TRANSIT.value,
                                 TransferStatus.RECEIVED_WITH_DISCREPANCY.value]),
        )
    ).scalars()
    total = 0
    for t in rows:
        total += t.quantity if t.status == TransferStatus.APPROVED else t.qty_in_transit
    return total


def coverage(db: Session, location_id: int, product_id: int,
             allocation: ConsignmentAllocation | None = None) -> Coverage:
    if allocation is None:
        allocation = db.execute(
            select(ConsignmentAllocation).where(
                ConsignmentAllocation.location_id == location_id, ConsignmentAllocation.product_id == product_id
            )
        ).scalar_one_or_none()
    outstanding, transit = open_outstanding(db, location_id, product_id)
    active = allocation is not None and allocation.is_active
    return Coverage(
        target=allocation.target_qty if active else None,
        auto_replenish=bool(active and allocation.auto_replenish),
        on_hand=get_balance(db, location_id, product_id).on_hand,
        open_outstanding=outstanding,
        in_transit_replenishment=transit,
        inbound_transfers=inbound_transfers(db, location_id, product_id),
    )


# ---------------------------------------------------------------------------
# Creating demand
# ---------------------------------------------------------------------------


def _create(
    db: Session, actor_id: int | None, *, location: Location, product_id: int, qty: int,
    reason: ReplenishmentReason, origin: Ref | None, sale_line_id: int | None = None,
    transfer_id: int | None = None, priority: Priority = Priority.NORMAL, expected_date: date | None = None,
    notes: str | None = None, auto_allocate: bool | None = None,
) -> ReplenishmentRequest:
    if location.type != LocationType.CONSIGNMENT:
        raise BusinessRuleError(f"Replenishment can only be raised for {vocab.aPartner} consignment location")
    if qty <= 0:
        raise BusinessRuleError("Replenishment quantity must be positive")
    held_before = db.execute(select(InventoryEntry.id).where(
        InventoryEntry.location_id == location.id, InventoryEntry.product_id == product_id).limit(1)).first()
    req = ReplenishmentRequest(
        first_supply=held_before is None,
        number=next_number(db, "REP"), reseller_id=location.reseller_id, location_id=location.id,
        product_id=product_id, reason=reason, origin_type=origin.type if origin else None,
        origin_id=origin.id if origin else None, origin_number=origin.number if origin else None,
        sale_line_id=sale_line_id, transfer_id=transfer_id, qty_required=qty, priority=priority,
        expected_date=expected_date, notes=notes, created_by_user_id=actor_id,
    )
    db.add(req)
    db.flush()
    _event(db, req, "CREATED", qty, actor_id, origin, notes)
    _refresh(req)
    record_audit(db, actor_id=actor_id, action="replenishment.create", entity_type="replenishment_request",
                 entity_id=req.id, reseller_id=req.reseller_id,
                 summary=f"{req.number}: {qty} required ({reason}) from {origin.number if origin else 'manual'}")
    wanted = auto_allocate if auto_allocate is not None else get_settings().auto_allocate_on_create
    reseller = db.get(Reseller, req.reseller_id)
    # Do not tie up warehouse stock for accounts that cannot currently receive dispatches (A-013).
    if wanted and reseller is not None and reseller.status == ResellerStatus.ACTIVE:
        try_allocate(db, actor_id, req)
    return req


def request_for_sale(db: Session, actor_id: int | None, *, location: Location, product_id: int, sold_qty: int,
                     sale_line_id: int, origin: Ref) -> ReplenishmentRequest | None:
    """Sale-triggered replacement of the same tyre (P-017).

    Without an active target the sold quantity is replaced one for one. With an active target the replacement is
    capped by the uncovered shortfall (A-001), and none is raised when auto-replenish is switched off for the SKU.
    """
    allocation = lock_allocation(db, location.id, product_id)  # serialise shortfall computation
    if allocation is not None and allocation.is_active:
        if not allocation.auto_replenish:
            return None
        qty = min(sold_qty, coverage(db, location.id, product_id, allocation).shortfall)
    else:
        qty = sold_qty
    if qty <= 0:
        return None
    return _create(db, actor_id, location=location, product_id=product_id, qty=qty,
                   reason=ReplenishmentReason.SALE, origin=origin, sale_line_id=sale_line_id)


def request_for_transfer(db: Session, actor_id: int | None, *, transfer: Transfer, qty: int,
                         source: Location) -> ReplenishmentRequest:
    """Replacement obligation to the source reseller of a transfer (not capped by target, A-003)."""
    return _create(db, actor_id, location=source, product_id=transfer.product_id, qty=qty,
                   reason=ReplenishmentReason.TRANSFER, origin=Ref("transfer", transfer.id, transfer.number),
                   transfer_id=transfer.id, priority=Priority.HIGH if transfer.urgency == Priority.URGENT
                   else Priority.NORMAL, notes=f"Replace stock transferred out on {transfer.number}")


def create_manual(db: Session, actor: User, *, location_id: int, product_id: int, qty: int, reason: str,
                  priority: Priority = Priority.NORMAL, expected_date: date | None = None,
                  approver_note: str | None = None) -> ReplenishmentRequest:
    location = db.get(Location, location_id)
    if location is None or location.type != LocationType.CONSIGNMENT:
        raise BusinessRuleError(f"Choose {vocab.aPartner} consignment location")
    ensure_reseller_access(actor, location.reseller_id, "Location")   # reseller users: own locations only
    if actor.is_reseller_user and priority == Priority.URGENT:
        raise BusinessRuleError(f"Urgent priority is set by {get_settings().company_name} staff; request High priority instead")
    _require_active_reseller(db, location)
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise BusinessRuleError("Product not found or inactive")
    allocation = lock_allocation(db, location.id, product_id)
    cov = coverage(db, location.id, product_id, allocation)
    if qty > cov.shortfall and not role_has(actor.role, P.REPLENISHMENT_OVERRIDE):
        raise BusinessRuleError(
            f"Requested {qty} exceeds the uncovered shortfall of {cov.shortfall} "
            f"(target {cov.target or 0}, on hand {cov.on_hand}, open demand {cov.open_outstanding}, "
            f"inbound transfers {cov.inbound_transfers}). Override permission is required."
        )
    # Requests raised by resellers and sales representatives reserve nothing until the Central Team
    # allocates stock (approval gate, P-008). Staff requests keep the configured auto-allocation.
    needs_approval = Role(actor.role) in (Role.RESELLER, Role.SALES_REP)
    approver_note = ((approver_note or "").strip() or None) if needs_approval else None
    notes = reason + (f"\n\nNote for the approver: {approver_note}" if approver_note else "")
    req = _create(db, actor.id, location=location, product_id=product_id, qty=qty,
                  reason=ReplenishmentReason.MANUAL, origin=None, priority=priority, expected_date=expected_date,
                  notes=notes, auto_allocate=False if needs_approval else None)
    if needs_approval:
        reseller = db.get(Reseller, req.reseller_id)
        _notify(db, staff_with(db, P.REPLENISHMENT_APPROVE), f"{req.number} is waiting for approval",
                f"{qty} × {product.tyre_label} for {reseller.business_name} · raised by {actor.full_name}"
                + (f" · {approver_note}" if approver_note else ""), req, exclude=actor.id)
    return req


def generate_shortfalls(db: Session, actor: User, *, reseller_id: int | None = None,
                        location_id: int | None = None) -> list[ReplenishmentRequest]:
    """Create TARGET_SHORTFALL requests for every allocation whose target is not covered."""
    stmt = (
        select(ConsignmentAllocation.id, ConsignmentAllocation.location_id, ConsignmentAllocation.product_id)
        .join(Location, Location.id == ConsignmentAllocation.location_id)
        .join(Reseller, Reseller.id == Location.reseller_id)
        .where(ConsignmentAllocation.is_active.is_(True), ConsignmentAllocation.target_qty > 0,
               Location.is_active.is_(True), Reseller.status == ResellerStatus.ACTIVE)
        .order_by(ConsignmentAllocation.location_id, ConsignmentAllocation.product_id)
    )
    if reseller_id is not None:
        stmt = stmt.where(Location.reseller_id == reseller_id)
    if location_id is not None:
        stmt = stmt.where(ConsignmentAllocation.location_id == location_id)
    created = []
    for _, loc_id, prod_id in db.execute(stmt).all():
        allocation = lock_allocation(db, loc_id, prod_id)
        cov = coverage(db, loc_id, prod_id, allocation)
        if cov.shortfall > 0:
            created.append(_create(
                db, actor.id, location=db.get(Location, loc_id), product_id=prod_id, qty=cov.shortfall,
                reason=ReplenishmentReason.TARGET_SHORTFALL, origin=Ref("allocation", allocation.id, None),
                notes="Restore agreed consignment target",
            ))
    return created


def _require_active_reseller(db: Session, location: Location) -> None:
    reseller = db.get(Reseller, location.reseller_id)
    if reseller is None or reseller.status != ResellerStatus.ACTIVE:
        raise BusinessRuleError(f"{vocab.Partner} account is {reseller.status if reseller else 'missing'}")


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------


def try_allocate(db: Session, actor_id: int | None, req: ReplenishmentRequest, qty: int | None = None,
                 warehouse: Location | None = None) -> ReplenishmentAllocation | None:
    """Reserve up to qty (default: all awaiting supply) of available warehouse stock. Returns None if none."""
    req = lock_request(db, req.id)
    if req.status not in OPEN_STATUSES:
        raise ConflictError(f"{req.number} is {req.status}")
    wanted = req.qty_awaiting_supply if qty is None else min(qty, req.qty_awaiting_supply)
    if wanted <= 0:
        return None
    warehouse = warehouse or default_warehouse(db)
    available = get_balance(db, warehouse.id, req.product_id).available
    take = min(wanted, available)
    if take <= 0:
        return None
    ledger = Ledger(db, TxnType.RESERVATION, actor_id=actor_id, ref=Ref("replenishment_request", req.id, req.number))
    reservation = ledger.reserve(warehouse, req.product_id, take, ReservationPurpose.REPLENISHMENT,
                                 Ref("replenishment_request", req.id, req.number))
    alloc = ReplenishmentAllocation(request_id=req.id, reservation_id=reservation.id,
                                    warehouse_location_id=warehouse.id, quantity=take, created_by_user_id=actor_id)
    db.add(alloc)
    req.qty_allocated += take
    _refresh(req)
    db.flush()
    _event(db, req, "ALLOCATED", take, actor_id, Ref("warehouse", warehouse.id, warehouse.code))
    _sync_stock_requests(db, [req.id])
    return alloc


def allocate(db: Session, actor: User, request_id: int, qty: int | None = None,
             warehouse_location_id: int | None = None) -> ReplenishmentAllocation:
    req = lock_request(db, request_id)
    warehouse = None
    if warehouse_location_id is not None:
        warehouse = db.get(Location, warehouse_location_id)
        if warehouse is None or warehouse.type != LocationType.WAREHOUSE:
            raise BusinessRuleError("Allocation source must be a warehouse")
    if req.qty_awaiting_supply <= 0:
        raise ConflictError(f"{req.number} has nothing awaiting supply")
    if qty is not None and qty > req.qty_awaiting_supply:
        raise BusinessRuleError(f"Only {req.qty_awaiting_supply} is awaiting supply on {req.number}")
    alloc = try_allocate(db, actor.id, req, qty, warehouse)
    if alloc is None:
        raise ConflictError("No warehouse stock is available to allocate", code="insufficient_stock")
    if qty is not None and alloc.quantity < qty:
        raise ConflictError(f"Only {alloc.quantity} available; requested {qty}", code="insufficient_stock")
    return alloc


def lock_allocation_row(db: Session, allocation_id: int) -> ReplenishmentAllocation:
    alloc = db.execute(
        select(ReplenishmentAllocation).where(ReplenishmentAllocation.id == allocation_id)
        .with_for_update().execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if alloc is None:
        raise NotFoundError("Allocation not found")
    return alloc


def release_allocation(db: Session, actor_id: int | None, allocation_id: int, reason: str) -> int:
    unlocked = db.get(ReplenishmentAllocation, allocation_id)
    if unlocked is None:
        raise NotFoundError("Allocation not found")
    req = lock_request(db, unlocked.request_id)  # lock order: request, then allocation
    alloc = lock_allocation_row(db, allocation_id)
    qty = alloc.open_qty
    if qty <= 0:
        raise ConflictError("Allocation has nothing left to release")
    reservation = db.get(StockReservation, alloc.reservation_id)
    ledger = Ledger(db, TxnType.RESERVATION_RELEASE, actor_id=actor_id, reason=reason,
                    ref=Ref("replenishment_request", req.id, req.number))
    ledger.release(reservation, qty)
    alloc.released_qty += qty
    alloc.status = AllocationStatus.RELEASED if alloc.dispatched_qty == 0 else AllocationStatus.CLOSED
    req.qty_allocated -= qty
    _refresh(req)
    _event(db, req, "ALLOCATION_RELEASED", qty, actor_id, reason=reason)
    db.flush()
    _sync_stock_requests(db, [req.id])
    return qty


@dataclass
class Proposal:
    request_id: int
    request_number: str
    reseller_id: int
    location_id: int
    product_id: int
    priority: Priority
    created_at: datetime
    awaiting_supply: int
    proposed_qty: int


def allocation_proposal(db: Session, *, warehouse_location_id: int | None = None,
                        product_id: int | None = None) -> list[Proposal]:
    """Propose allocation of available warehouse stock to open backorders (policy: PRIORITY_THEN_OLDEST).

    Nothing is reserved until a user confirms (BC §10: not automatically assigned).
    """
    warehouse = db.get(Location, warehouse_location_id) if warehouse_location_id else default_warehouse(db)
    stmt = (
        select(ReplenishmentRequest)
        .join(Reseller, Reseller.id == ReplenishmentRequest.reseller_id)
        .where(ReplenishmentRequest.status.in_([s.value for s in OPEN_STATUSES]),
               Reseller.status == ResellerStatus.ACTIVE)
    )
    if product_id is not None:
        stmt = stmt.where(ReplenishmentRequest.product_id == product_id)
    requests = [r for r in db.execute(stmt).scalars() if r.qty_awaiting_supply > 0]
    requests.sort(key=lambda r: (PRIORITY_RANK[r.priority], r.created_at, r.id))
    remaining: dict[int, int] = {}
    proposals = []
    for r in requests:
        if r.product_id not in remaining:
            remaining[r.product_id] = get_balance(db, warehouse.id, r.product_id).available
        take = min(r.qty_awaiting_supply, remaining[r.product_id])
        if take <= 0:
            continue
        remaining[r.product_id] -= take
        proposals.append(Proposal(r.id, r.number, r.reseller_id, r.location_id, r.product_id, r.priority,
                                  r.created_at, r.qty_awaiting_supply, take))
    return proposals


def confirm_allocations(db: Session, actor: User, lines: list[tuple[int, int]],
                        warehouse_location_id: int | None = None) -> list[ReplenishmentAllocation]:
    out = []
    for request_id, qty in sorted(lines):
        out.append(allocate(db, actor, request_id, qty, warehouse_location_id))
    record_audit(db, actor_id=actor.id, action="replenishment.allocate_batch", entity_type="replenishment_request",
                 entity_id=None, summary=f"Confirmed {len(out)} allocations ({sum(a.quantity for a in out)} units)")
    return out


# ---------------------------------------------------------------------------
# Changes and cancellation
# ---------------------------------------------------------------------------


def cancel_open_quantity(db: Session, actor_id: int | None, req: ReplenishmentRequest, qty: int, reason: str,
                         ref: Ref | None = None, release_allocations: bool = False) -> int:
    """Cancel up to qty of the not-yet-dispatched quantity. Returns the quantity actually cancelled."""
    req = lock_request(db, req.id)
    if req.status not in OPEN_STATUSES or qty <= 0:
        return 0
    if release_allocations and req.qty_awaiting_supply < qty:
        active = db.execute(
            select(ReplenishmentAllocation.id).where(
                ReplenishmentAllocation.request_id == req.id,
                ReplenishmentAllocation.status == AllocationStatus.ACTIVE,
            ).order_by(ReplenishmentAllocation.id.desc())
        ).scalars().all()
        for alloc_id in active:
            if req.qty_awaiting_supply >= qty:
                break
            release_allocation(db, actor_id, alloc_id, reason)
            req = lock_request(db, req.id)
    take = min(qty, req.qty_awaiting_supply)
    if take <= 0:
        return 0
    req.qty_cancelled += take
    _refresh(req)
    _event(db, req, "CANCELLED", take, actor_id, ref, reason)
    db.flush()
    _sync_stock_requests(db, [req.id])
    return take


def cancel(db: Session, actor: User, request_id: int, qty: int | None, reason: str) -> ReplenishmentRequest:
    req = lock_request(db, request_id)
    if req.status not in OPEN_STATUSES:
        raise ConflictError(f"{req.number} is already {req.status}")
    qty = req.qty_awaiting_supply if qty is None else qty
    if qty <= 0 or qty > req.qty_awaiting_supply:
        raise BusinessRuleError(
            f"Only the {req.qty_awaiting_supply} unit(s) awaiting supply can be cancelled; release allocations "
            "or resolve deliveries first"
        )
    cancel_open_quantity(db, actor.id, req, qty, reason)
    record_audit(db, actor_id=actor.id, action="replenishment.cancel", entity_type="replenishment_request",
                 entity_id=req.id, reseller_id=req.reseller_id, summary=f"Cancelled {qty} on {req.number}: {reason}")
    return req


def update_planning(db: Session, actor: User, request_id: int, *, reason: str, priority: Priority | None = None,
                    expected_date: date | None = None, clear_expected_date: bool = False,
                    purchase_order_line_id: int | None = None) -> ReplenishmentRequest:
    req = lock_request(db, request_id)
    if req.status not in OPEN_STATUSES:
        raise ConflictError(f"{req.number} is {req.status}")
    changes = []
    if priority is not None and priority != req.priority:
        changes.append(f"priority {req.priority} → {priority}")
        _event(db, req, "PRIORITY_CHANGED", None, actor.id, reason=f"{req.priority} → {priority}: {reason}")
        req.priority = priority
    if purchase_order_line_id is not None:
        pol = db.get(PurchaseOrderLine, purchase_order_line_id)
        if pol is None or pol.product_id != req.product_id:
            raise BusinessRuleError("Purchase order line must be for the same product")
        req.purchase_order_line_id = pol.id
        if expected_date is None and not clear_expected_date and pol.purchase_order.expected_date:
            expected_date = pol.purchase_order.expected_date
        changes.append(f"linked to {pol.purchase_order.number}")
        _event(db, req, "SUPPLY_LINKED", None, actor.id,
               Ref("purchase_order", pol.purchase_order_id, pol.purchase_order.number), reason)
    if clear_expected_date or (expected_date is not None and expected_date != req.expected_date):
        new = None if clear_expected_date else expected_date
        changes.append(f"expected date {req.expected_date} → {new}")
        _event(db, req, "EXPECTED_DATE_CHANGED", None, actor.id, reason=f"{req.expected_date} → {new}: {reason}")
        req.expected_date = new
    if not changes:
        raise BusinessRuleError("Nothing to change")
    db.flush()
    record_audit(db, actor_id=actor.id, action="replenishment.update", entity_type="replenishment_request",
                 entity_id=req.id, reseller_id=req.reseller_id, summary=f"{req.number}: {', '.join(changes)} ({reason})")
    return req


# ---------------------------------------------------------------------------
# Fulfilment on the request itself (release 1.11, finding 22): approve, send to the RM, reject, ready, ship
# ---------------------------------------------------------------------------


def link(req: ReplenishmentRequest) -> str:
    return f"/replenishment/{req.id}"


def _notify(db: Session, user_ids, title: str, body: str | None, req: ReplenishmentRequest,
            exclude: int | None = None) -> None:
    notify_users(db, user_ids, title, body, link=link(req), entity_type="replenishment_request", entity_id=req.id,
                 exclude=exclude)


def _requester_audience(db: Session, req: ReplenishmentRequest) -> list[int | None]:
    """Who raised it, the dealer's own users and the dealer's sales representative."""
    reseller = db.get(Reseller, req.reseller_id)
    return [req.created_by_user_id, reseller.sales_rep_user_id if reseller else None,
            *reseller_users(db, req.reseller_id)]


def _fulfilment_request(db: Session, request_id: int) -> ReplenishmentRequest:
    """Lock the request; requests created by a stock request are driven from that stock request (409)."""
    req = lock_request(db, request_id)
    if req.reason == ReplenishmentReason.STOCK_REQUEST:
        raise ConflictError(f"Managed on {req.origin_number or 'its stock request'}", code="managed_on_stock_request")
    if req.status not in OPEN_STATUSES:
        raise ConflictError(f"{req.number} is {req.status}")
    return req


def _awaiting_decision(req: ReplenishmentRequest) -> bool:
    return req.status in OPEN_STATUSES and req.qty_awaiting_supply > 0


def _guard_escalation(db: Session, actor: User, req: ReplenishmentRequest) -> None:
    """While a request waits for a Relationship Manager, only that RM or an Administrator may decide it."""
    if req.escalated_to_user_id and actor.id != req.escalated_to_user_id and actor.role != Role.ADMINISTRATOR:
        rm = db.get(User, req.escalated_to_user_id)
        raise PermissionDeniedError(f"Waiting for {rm.full_name if rm else 'the Relationship Manager'} to approve")


def _clear_escalation(req: ReplenishmentRequest) -> None:
    req.escalated_to_user_id = req.escalated_by_user_id = req.escalated_at = req.escalation_note = None


def approve(db: Session, actor: User, request_id: int, approval, qty: int | None = None,
            warehouse_location_id: int | None = None) -> ReplenishmentRequest:
    """Allocate warehouse stock (as allocate()) and record who approved it, how, with whom and why."""
    _require(actor, P.REPLENISHMENT_APPROVE)
    req = _fulfilment_request(db, request_id)
    _guard_escalation(db, actor, req)
    alloc = allocate(db, actor, request_id, qty, warehouse_location_id)
    req = lock_request(db, request_id)
    req.approval_method, req.approval_contact, req.approval_comments = \
        approval.method.value, approval.contact, approval.comments
    req.approved_by_user_id, req.approved_at = actor.id, _now()
    _clear_escalation(req)
    contact = f" with {approval.contact}" if approval.contact else ""
    _event(db, req, "APPROVED", alloc.quantity, actor.id,
           reason=f"{approval.method.value.replace('_', ' ').capitalize()}{contact}: {approval.comments}")
    db.flush()
    record_audit(db, actor_id=actor.id, action="replenishment.approve", entity_type="replenishment_request",
                 entity_id=req.id, reseller_id=req.reseller_id,
                 summary=f"Approved {alloc.quantity} on {req.number} ({approval.method.value}{contact})",
                 details={"approval": {"method": approval.method.value, "contact": approval.contact,
                                       "comments": approval.comments}, "quantity": alloc.quantity})
    product = db.get(Product, req.product_id)
    _notify(db, _requester_audience(db, req), f"{req.number} approved",
            f"{alloc.quantity} × {product.tyre_label} reserved at the warehouse", req, exclude=actor.id)
    reseller = db.get(Reseller, req.reseller_id)
    _notify(db, staff_in_roles(db, Role.WAREHOUSE_MANAGER, Role.ADMINISTRATOR), f"{req.number} approved — ready to pick",
            f"{alloc.quantity} unit(s) reserved for {reseller.business_name}", req, exclude=actor.id)
    return req


def escalate(db: Session, actor: User, request_id: int, to_user_id: int, note: str | None) -> ReplenishmentRequest:
    """Send a request to a Relationship Manager for approval; the warehouse continues once it is approved."""
    _require(actor, P.REPLENISHMENT_APPROVE)
    req = _fulfilment_request(db, request_id)
    if not _awaiting_decision(req):
        raise ConflictError(f"{req.number} has nothing waiting for a decision")
    if req.escalated_to_user_id:
        raise ConflictError(f"{req.number} is already waiting for a Relationship Manager")
    rm = db.get(User, to_user_id)
    if rm is None or not rm.is_active or rm.role != Role.RELATIONSHIP_MANAGER:
        raise BusinessRuleError("Choose an active Relationship Manager")
    req.escalated_to_user_id, req.escalated_by_user_id, req.escalated_at = rm.id, actor.id, _now()
    req.escalation_note = (note or "").strip() or None
    note_tail = f": {req.escalation_note}" if req.escalation_note else ""
    _event(db, req, "ESCALATED", None, actor.id, reason=f"Sent to {rm.full_name} for approval{note_tail}")
    db.flush()
    record_audit(db, actor_id=actor.id, action="replenishment.escalate", entity_type="replenishment_request",
                 entity_id=req.id, reseller_id=req.reseller_id, summary=f"{req.number} sent to {rm.full_name}{note_tail}")
    reseller = db.get(Reseller, req.reseller_id)
    _notify(db, [rm.id], f"Your approval is needed: {req.number}",
            f"{reseller.business_name} · sent by {actor.full_name}{note_tail}", req)
    return req


def hand_back(db: Session, actor: User, request_id: int, note: str | None) -> ReplenishmentRequest:
    """The Relationship Manager (or an Administrator) returns the decision to the warehouse."""
    _require(actor, P.REPLENISHMENT_APPROVE)
    req = _fulfilment_request(db, request_id)
    if not req.escalated_to_user_id:
        raise ConflictError(f"{req.number} is not waiting for a Relationship Manager")
    _guard_escalation(db, actor, req)
    by = req.escalated_by_user_id
    _clear_escalation(req)
    note = (note or "").strip() or None
    _event(db, req, "HANDED_BACK", None, actor.id,
           reason="Handed back to the warehouse" + (f": {note}" if note else ""))
    db.flush()
    record_audit(db, actor_id=actor.id, action="replenishment.hand_back", entity_type="replenishment_request",
                 entity_id=req.id, reseller_id=req.reseller_id, summary=f"{req.number} handed back")
    _notify(db, [by], f"{req.number} handed back to you", note or f"{actor.full_name} handed the decision back", req,
            exclude=actor.id)
    return req


def reject(db: Session, actor: User, request_id: int, reason: str) -> ReplenishmentRequest:
    """Cancel everything still awaiting supply. The dealer gets the kind standard message, never the reason."""
    _require(actor, P.REPLENISHMENT_APPROVE)
    req = _fulfilment_request(db, request_id)
    _guard_escalation(db, actor, req)
    if req.qty_awaiting_supply <= 0:
        raise ConflictError(f"{req.number} has nothing awaiting supply to reject")
    reason = reason.strip()
    qty = cancel_open_quantity(db, actor.id, req, req.qty_awaiting_supply, "Not supplied")
    req = lock_request(db, request_id)
    _clear_escalation(req)
    _event(db, req, "REJECTED", qty, actor.id, reason=reason)
    db.flush()
    record_audit(db, actor_id=actor.id, action="replenishment.reject", entity_type="replenishment_request",
                 entity_id=req.id, reseller_id=req.reseller_id, summary=f"Rejected {qty} on {req.number}: {reason}")
    kind_audience = {req.created_by_user_id, *reseller_users(db, req.reseller_id)}
    supplied = req.qty_allocated + req.qty_in_transit + req.qty_delivered
    body = KIND_REJECTION + (f" {supplied} {vocab.item}(s) of this request are being supplied." if supplied else "")
    _notify(db, kind_audience, f"Update on your request {req.number}", body, req, exclude=actor.id)
    _notify(db, [u for u in _requester_audience(db, req) if u not in kind_audience],
            f"{req.number} rejected", f"{qty} not supplied: {reason}", req, exclude=actor.id)
    return req


def mark_ready(db: Session, actor: User, request_id: int) -> ReplenishmentRequest:
    _require(actor, P.DISPATCH)
    req = _fulfilment_request(db, request_id)
    if req.qty_allocated <= 0:
        raise ConflictError("Nothing is reserved to prepare for shipment")
    req.ready_at, req.ready_by_user_id = _now(), actor.id
    _event(db, req, "READY_FOR_SHIPMENT", req.qty_allocated, actor.id,
           reason=f"Picked and packed: {req.qty_allocated} unit(s) ready for shipment")
    db.flush()
    _notify(db, _requester_audience(db, req), f"{req.number} is ready for shipment",
            f"{req.qty_allocated} unit(s) packed at the warehouse", req, exclude=actor.id)
    return req


def _address(location: Location) -> str | None:
    parts = [location.address_line1, location.address_line2, location.city, location.region, location.postcode,
             location.country]
    text = ", ".join(p for p in parts if p)
    return f"{location.name}, {text}" if text else location.name


def ship(db: Session, actor: User, request_id: int, *, shipping_method: str = "COURIER", carrier: str | None = None,
         tracking_number: str | None = None, carried_by_user_id: int | None = None, notes: str | None = None,
         qty: int | None = None) -> Delivery:
    """Ship reserved stock for this request (wraps dispatch) and tell the requester and the carrying rep."""
    _require(actor, P.DISPATCH)
    req = _fulfilment_request(db, request_id)
    if shipping_method == "COURIER" and (not carrier or not carrier.strip()):
        raise BusinessRuleError("Enter the carrier")
    if req.qty_allocated <= 0:
        raise BusinessRuleError("Nothing reserved to ship")
    location = db.get(Location, req.location_id)
    delivery = dispatch(db, actor, to_location_id=req.location_id, lines=[(req.id, qty)],
                        carrier_reference=(carrier or "").strip() or None, notes=notes,
                        tracking_number=tracking_number, shipping_address=_address(location),
                        shipping_method=shipping_method, carried_by_user_id=carried_by_user_id)
    req = lock_request(db, request_id)
    req.ready_at = req.ready_by_user_id = None
    units = sum(ln.qty_dispatched for ln in delivery.lines)
    via = delivery.carrier_reference or carrier
    track = f", tracking {tracking_number}" if tracking_number else ""
    db.flush()
    _notify(db, _requester_audience(db, req), f"{req.number} has shipped",
            f"{units} unit(s) on {delivery.number} via {via}{track}", req, exclude=actor.id)
    if delivery.carried_by_user_id:
        _notify(db, [delivery.carried_by_user_id], f"Please deliver {delivery.number}",
                f"{units} unit(s) for {db.get(Reseller, req.reseller_id).business_name}. Confirm delivery on "
                "arrival.", req, exclude=actor.id)
    return delivery


# ---------------------------------------------------------------------------
# Dispatch and delivery
# ---------------------------------------------------------------------------


def dispatch(db: Session, actor: User, *, to_location_id: int, lines: list[tuple[int, int | None]],
             carrier_reference: str | None = None, notes: str | None = None, tracking_number: str | None = None,
             shipping_address: str | None = None, stock_request_id: int | None = None,
             shipping_method: str = "COURIER", carried_by_user_id: int | None = None) -> Delivery:
    """Dispatch allocated stock for one or more requests of the same reseller location.

    lines: (request_id, qty or None for all allocated). Consumes reservations oldest-first.
    """
    to_loc = db.get(Location, to_location_id)
    if to_loc is None or to_loc.type != LocationType.CONSIGNMENT:
        raise BusinessRuleError(f"Destination must be {vocab.aPartner} consignment location")
    _require_active_reseller(db, to_loc)
    if not lines:
        raise BusinessRuleError("Nothing to dispatch")
    carrier_reference = _shipping(db, shipping_method, carried_by_user_id, carrier_reference)
    transit = system_location(db, LocationType.TRANSIT)

    plan: list[tuple[ReplenishmentRequest, ReplenishmentAllocation, int]] = []
    warehouse_id: int | None = None
    for request_id, qty in sorted(lines, key=lambda x: x[0]):
        req = lock_request(db, request_id)
        if req.location_id != to_loc.id:
            raise BusinessRuleError(f"{req.number} is for a different location")
        if req.status not in OPEN_STATUSES:
            raise ConflictError(f"{req.number} is {req.status}")
        want = req.qty_allocated if qty is None else qty
        if want <= 0 or want > req.qty_allocated:
            raise ConflictError(f"{req.number} has {req.qty_allocated} allocated; cannot dispatch {want}")
        allocs = db.execute(
            select(ReplenishmentAllocation)
            .where(ReplenishmentAllocation.request_id == req.id,
                   ReplenishmentAllocation.status == AllocationStatus.ACTIVE)
            .order_by(ReplenishmentAllocation.id).with_for_update()
        ).scalars().all()
        for alloc in allocs:
            if want <= 0:
                break
            if warehouse_id is None:
                warehouse_id = alloc.warehouse_location_id
            if alloc.warehouse_location_id != warehouse_id:
                continue  # one delivery per source warehouse
            take = min(want, alloc.open_qty)
            plan.append((req, alloc, take))
            want -= take
        if want > 0:
            raise ConflictError(f"{req.number}: allocated stock is split across warehouses; dispatch separately")

    warehouse = db.get(Location, warehouse_id)
    delivery = Delivery(number=next_number(db, "DEL"), from_location_id=warehouse.id, to_location_id=to_loc.id,
                        reseller_id=to_loc.reseller_id, carrier_reference=carrier_reference, notes=notes,
                        tracking_number=tracking_number, shipping_address=shipping_address,
                        stock_request_id=stock_request_id, dispatched_by_user_id=actor.id,
                        shipping_method=shipping_method,
                        carried_by_user_id=carried_by_user_id if shipping_method == "SALES_REP" else None,
                        status=DeliveryStatus.IN_TRANSIT)
    db.add(delivery)
    db.flush()
    ref = Ref("delivery", delivery.id, delivery.number)
    ledger = Ledger(db, TxnType.REPLENISHMENT_DISPATCH, actor_id=actor.id, ref=ref, notes=notes)
    delivery.dispatch_transaction_id = ledger.txn.id
    for req, alloc, take in plan:
        reservation = db.get(StockReservation, alloc.reservation_id)
        ledger.move(req.product_id, warehouse, transit, take, reservation=reservation)
        alloc.dispatched_qty += take
        if alloc.open_qty == 0:
            alloc.status = AllocationStatus.DISPATCHED if alloc.released_qty == 0 else AllocationStatus.CLOSED
        req.qty_allocated -= take
        req.qty_in_transit += take
        if req.qty_allocated == 0:
            req.ready_at = req.ready_by_user_id = None   # nothing left packed and waiting
        _refresh(req)
        db.add(DeliveryLine(delivery_id=delivery.id, request_id=req.id, allocation_id=alloc.id,
                            product_id=req.product_id, qty_dispatched=take))
        _event(db, req, "DISPATCHED", take, actor.id, ref)
    db.flush()
    record_audit(db, actor_id=actor.id, action="delivery.dispatch", entity_type="delivery", entity_id=delivery.id,
                 reseller_id=delivery.reseller_id,
                 summary=f"Dispatched {delivery.number} to {to_loc.code}: {sum(p[2] for p in plan)} units")
    _sync_stock_requests(db, [p[0].id for p in plan])
    db.refresh(delivery)
    return delivery


def _shipping(db: Session, method: str, carried_by_user_id: int | None, carrier: str | None) -> str | None:
    """Validate how a shipment travels; returns the carrier text recorded on the delivery."""
    if method == "COURIER":
        return carrier
    if method != "SALES_REP":
        raise BusinessRuleError("Shipping method must be COURIER or SALES_REP")
    rep = db.get(User, carried_by_user_id) if carried_by_user_id else None
    if rep is None or not rep.is_active or rep.role != Role.SALES_REP:
        raise BusinessRuleError(f"Choose the sales representative who will carry the {vocab.items}")
    return f"Sales representative: {rep.full_name}"


def lock_delivery(db: Session, delivery_id: int) -> Delivery:
    d = db.execute(select(Delivery).where(Delivery.id == delivery_id).with_for_update()
                   .execution_options(populate_existing=True)).scalar_one_or_none()
    if d is None:
        raise NotFoundError("Delivery not found")
    return d


def receive_delivery(db: Session, actor: User, delivery_id: int, received: dict[int, int] | None,
                     notes: str | None = None, delivered_on: date | None = None,
                     delivery_reference: str | None = None, received_by_name: str | None = None,
                     photos: list[str] | None = None) -> Delivery:
    """Confirm receipt at the reseller. received: {delivery_line_id: qty}; omitted lines = fully received."""
    delivery = lock_delivery(db, delivery_id)
    ensure_reseller_access(actor, delivery.reseller_id, "Delivery")   # reseller users: own deliveries only
    # Carried by a Sales Rep: only the dealer or that Sales Rep confirms; a Sales Rep records who took it.
    proofs.ensure_can_confirm(db, actor, reseller_id=delivery.reseller_id, what="Delivery",
                              carried_by_user_id=delivery.carried_by_user_id if delivery.shipping_method == "SALES_REP"
                              else None)
    received_by_name, notes = proofs.receipt_details(actor, received_by_name, notes)
    if delivered_on is not None and delivered_on > date.today():
        raise BusinessRuleError("Delivery date cannot be in the future")
    if delivery.status != DeliveryStatus.IN_TRANSIT:
        raise ConflictError(f"{delivery.number} has already been received")
    received = received or {}
    unknown = set(received) - {ln.id for ln in delivery.lines}
    if unknown:
        raise BusinessRuleError(f"Lines {sorted(unknown)} are not on {delivery.number}")
    to_loc = db.get(Location, delivery.to_location_id)
    transit = system_location(db, LocationType.TRANSIT)
    ref = Ref("delivery", delivery.id, delivery.number)
    ledger = Ledger(db, TxnType.REPLENISHMENT_RECEIPT, actor_id=actor.id, ref=ref, notes=notes)
    discrepancy = False
    for line in delivery.lines:
        qty = received.get(line.id, line.qty_dispatched)
        if qty < 0 or qty > line.qty_dispatched:
            raise BusinessRuleError(f"Received quantity for line {line.id} must be 0–{line.qty_dispatched}")
        req = lock_request(db, line.request_id)
        if qty > 0:
            ledger.move(line.product_id, transit, to_loc, qty)
            req.qty_in_transit -= qty
            req.qty_delivered += qty
            _event(db, req, "DELIVERED", qty, actor.id, ref)
        line.qty_received = qty
        if qty < line.qty_dispatched:
            discrepancy = True
            _event(db, req, "SHORT_DELIVERED", line.qty_dispatched - qty, actor.id, ref,
                   "Short delivery; quantity remains in transit until resolved")
        _refresh(req)
    delivery.status = DeliveryStatus.RECEIVED_WITH_DISCREPANCY if discrepancy else DeliveryStatus.RECEIVED
    delivery.received_at = _now()
    delivery.received_by_user_id = actor.id
    delivery.delivered_on = delivered_on or delivery.received_at.date()
    delivery.delivery_reference = delivery_reference
    delivery.receipt_notes = notes
    delivery.received_by_name = received_by_name
    for data_url in photos or []:
        proofs.add_photo(db, actor, "delivery", delivery.id, data_url)
    db.flush()
    _sync_stock_requests(db, [ln.request_id for ln in delivery.lines])
    record_audit(db, actor_id=actor.id, action="delivery.receive", entity_type="delivery", entity_id=delivery.id,
                 reseller_id=delivery.reseller_id,
                 summary=f"Received {delivery.number}" + (" with discrepancy" if discrepancy else ""))
    return delivery


def resolve_delivery_line(db: Session, actor: User, delivery_id: int, line_id: int, outcome: str, qty: int,
                          reason: str) -> Delivery:
    """Resolve quantity still in transit after a short receipt.

    RETURN_TO_WAREHOUSE and LOST put the quantity back to awaiting supply on the request; LATE_DELIVERY delivers it.
    """
    delivery = lock_delivery(db, delivery_id)
    if delivery.status != DeliveryStatus.RECEIVED_WITH_DISCREPANCY:
        raise ConflictError(f"{delivery.number} has no open discrepancy")
    line = next((ln for ln in delivery.lines if ln.id == line_id), None)
    if line is None:
        raise NotFoundError("Delivery line not found")
    if qty <= 0 or qty > line.qty_open:
        raise BusinessRuleError(f"Line has {line.qty_open} unresolved")
    if outcome == "LOST":
        _require(actor, P.INVENTORY_ADJUST)
    req = lock_request(db, line.request_id)
    transit = system_location(db, LocationType.TRANSIT)
    ref = Ref("delivery", delivery.id, delivery.number)
    ledger = Ledger(db, TxnType.TRANSIT_RESOLUTION, actor_id=actor.id, ref=ref, reason=f"{outcome}: {reason}",
                    approved_by_id=actor.id)
    if outcome == "RETURN_TO_WAREHOUSE":
        ledger.move(line.product_id, transit, db.get(Location, delivery.from_location_id), qty)
        line.qty_returned += qty
        req.qty_in_transit -= qty
        _event(db, req, "RETURNED", qty, actor.id, ref, reason)
    elif outcome == "LOST":
        ledger.move(line.product_id, transit, system_location(db, LocationType.ADJUSTMENT), qty)
        line.qty_lost += qty
        req.qty_in_transit -= qty
        _event(db, req, "LOST", qty, actor.id, ref, reason)
    elif outcome == "LATE_DELIVERY":
        ledger.move(line.product_id, transit, db.get(Location, delivery.to_location_id), qty)
        line.qty_late_received += qty
        req.qty_in_transit -= qty
        req.qty_delivered += qty
        _event(db, req, "DELIVERED", qty, actor.id, ref, f"Late delivery: {reason}")
    else:
        raise BusinessRuleError("Outcome must be RETURN_TO_WAREHOUSE, LOST or LATE_DELIVERY")
    _refresh(req)
    db.flush()
    if all(ln.qty_open == 0 for ln in delivery.lines):
        delivery.status = DeliveryStatus.CLOSED
    _sync_stock_requests(db, [req.id])
    record_audit(db, actor_id=actor.id, action="delivery.resolve", entity_type="delivery", entity_id=delivery.id,
                 reseller_id=delivery.reseller_id, summary=f"{delivery.number}: {outcome} {qty} ({reason})")
    return delivery
