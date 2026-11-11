from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.industry import vocab
from app.core.lookups import Names
from app.core.messages import KIND_REJECTION
from app.core.permissions import P, Role
from app.modules.delivery_notes import service as delivery_notes
from app.modules.identity.deps import DB, require
from app.modules.identity.models import User
from app.modules.identity.scoping import ensure_reseller_access, scoped_reseller_id
from app.modules.notifications.service import notify_users
from app.modules.proofs import service as proofs
from app.modules.replenishment import service
from app.modules.replenishment.models import (
    OPEN_STATUSES,
    AllocationStatus,
    Delivery,
    DeliveryLine,
    DeliveryStatus,
    ReplenishmentAllocation,
    ReplenishmentEvent,
    ReplenishmentReason,
    ReplenishmentRequest,
    ReplenishmentStatus,
)
from app.modules.replenishment.schemas import (
    AllocateIn,
    AllocationOut,
    ApproveIn,
    CancelIn,
    ConfirmAllocationsIn,
    CoverageOut,
    CoveringTransferOut,
    DeliveryLineOut,
    DeliveryOut,
    DispatchIn,
    EventOut,
    GenerateShortfallsIn,
    LinkedRequestOut,
    ManualRequestIn,
    PlanningIn,
    ProposalOut,
    ReceiveIn,
    RejectIn,
    ReleaseIn,
    RequestDetailOut,
    RequestOut,
    ResolveIn,
    ShipIn,
)
from app.modules.stock_requests.models import StockRequest
from app.modules.stock_requests.schemas import EscalateIn, HandBackIn

router = APIRouter(prefix="/replenishment", tags=["replenishment"])
Reader = Annotated[User, Depends(require(P.REPLENISHMENT_READ))]
Manager = Annotated[User, Depends(require(P.REPLENISHMENT_MANAGE))]
Requester = Annotated[User, Depends(require(P.REPLENISHMENT_REQUEST))]
Approver = Annotated[User, Depends(require(P.REPLENISHMENT_APPROVE))]
Dispatcher = Annotated[User, Depends(require(P.DISPATCH))]

APPROVAL_ROLES = (Role.RESELLER.value, Role.SALES_REP.value)
AUTO_APPROVED_REASONS = (ReplenishmentReason.SALE, ReplenishmentReason.TRANSFER)
# Staff-only history: dealers see the outcome, not who it was escalated to or the approval conversation.
STAFF_ONLY_EVENTS = {"ESCALATED", "HANDED_BACK", "READY_FOR_SHIPMENT"}


def requests_out(db, reqs: list[ReplenishmentRequest]) -> list[RequestOut]:
    names = Names(db)
    for r in reqs:
        names.add("reseller", r.reseller_id).add("location", r.location_id).add("product", r.product_id)
        names.add("user", r.created_by_user_id, r.approved_by_user_id, r.escalated_to_user_id,
                  r.escalated_by_user_id, r.ready_by_user_id)
    names.resolve()
    now = datetime.now(UTC)
    return [
        RequestOut(
            id=r.id, number=r.number, reseller_id=r.reseller_id, reseller_name=names.reseller_name(r.reseller_id),
            location_id=r.location_id, location_code=names.loc_code(r.location_id), product_id=r.product_id,
            sku=names.sku(r.product_id), product_name=names.product_name(r.product_id), reason=r.reason,
            origin_type=r.origin_type, origin_id=r.origin_id, origin_number=r.origin_number,
            sale_line_id=r.sale_line_id, transfer_id=r.transfer_id, qty_required=r.qty_required,
            qty_allocated=r.qty_allocated, qty_in_transit=r.qty_in_transit,
            qty_transfer_covered=r.qty_transfer_covered, qty_delivered=r.qty_delivered,
            qty_cancelled=r.qty_cancelled, qty_outstanding=r.qty_outstanding,
            qty_awaiting_supply=r.qty_awaiting_supply, priority=r.priority, expected_date=r.expected_date,
            purchase_order_line_id=r.purchase_order_line_id, status=r.status, notes=r.notes,
            created_at=r.created_at, closed_at=r.closed_at,
            age_days=((r.closed_at or now) - r.created_at).days,
            raised_by=names.user_name(r.created_by_user_id),
            first_supply=r.first_supply,
            raised_by_role=names.users[r.created_by_user_id].role.value if r.created_by_user_id in names.users else None,
            awaiting_approval=(r.reason == ReplenishmentReason.MANUAL and r.approved_at is None
                               and r.status in OPEN_STATUSES and r.qty_awaiting_supply > 0
                               and r.created_by_user_id in names.users
                               and names.users[r.created_by_user_id].role.value in APPROVAL_ROLES),
            auto_approved=(r.reason in AUTO_APPROVED_REASONS and r.approved_at is None
                           and r.qty_allocated + r.qty_in_transit + r.qty_delivered > 0),
            approved_by=names.user_name(r.approved_by_user_id), approved_at=r.approved_at,
            approval_method=r.approval_method, approval_contact=r.approval_contact,
            approval_comments=r.approval_comments, escalated_to_user_id=r.escalated_to_user_id,
            escalated_to=names.user_name(r.escalated_to_user_id), escalated_by=names.user_name(r.escalated_by_user_id),
            escalated_at=r.escalated_at, escalation_note=r.escalation_note,
            ready=r.ready_at is not None and r.qty_allocated > 0, ready_at=r.ready_at,
            ready_by=names.user_name(r.ready_by_user_id),
        )
        for r in reqs
    ]


def _for(user: User, rows: list[RequestOut]) -> list[RequestOut]:
    """Dealers never see approval conversations, escalations or who packed the order."""
    if not user.is_reseller_user:
        return rows
    hidden = dict(approval_method=None, approval_contact=None, approval_comments=None, escalated_to_user_id=None,
                  escalated_to=None, escalated_by=None, escalated_at=None, escalation_note=None, ready_by=None)
    return [r.model_copy(update=hidden) for r in rows]


def _events_for(user: User, events: list[EventOut]) -> list[EventOut]:
    if not user.is_reseller_user:
        return events
    out = []
    for e in events:
        if e.event_type in STAFF_ONLY_EVENTS:
            continue
        if e.event_type == "REJECTED":
            e = e.model_copy(update={"reason": KIND_REJECTION})
        elif e.event_type == "APPROVED":
            e = e.model_copy(update={"reason": None})
        out.append(e)
    return out


def deliveries_out(db, deliveries: list[Delivery]) -> list[DeliveryOut]:
    names = Names(db)
    req_ids = set()
    for d in deliveries:
        names.add("location", d.from_location_id, d.to_location_id).add("reseller", d.reseller_id)
        names.add("user", d.dispatched_by_user_id, d.received_by_user_id, d.carried_by_user_id)
        names.add("product", *[ln.product_id for ln in d.lines])
        req_ids |= {ln.request_id for ln in d.lines}
    names.resolve()
    req_numbers = dict(db.execute(
        select(ReplenishmentRequest.id, ReplenishmentRequest.number).where(ReplenishmentRequest.id.in_(req_ids))
    ).all()) if req_ids else {}
    sr_ids = {d.stock_request_id for d in deliveries if d.stock_request_id}
    sr_numbers = dict(db.execute(
        select(StockRequest.id, StockRequest.number).where(StockRequest.id.in_(sr_ids))
    ).all()) if sr_ids else {}
    photos = proofs.photo_ids(db, "delivery", [d.id for d in deliveries])
    retired = proofs.retired_counts(db, "delivery", [d.id for d in deliveries])
    return [
        DeliveryOut(
            id=d.id, number=d.number, from_location_id=d.from_location_id,
            from_location_code=names.loc_code(d.from_location_id), to_location_id=d.to_location_id,
            to_location_code=names.loc_code(d.to_location_id), reseller_id=d.reseller_id,
            reseller_name=names.reseller_name(d.reseller_id), status=d.status, carrier_reference=d.carrier_reference,
            dispatched_at=d.dispatched_at, dispatched_by=names.user_name(d.dispatched_by_user_id),
            received_at=d.received_at, received_by=names.user_name(d.received_by_user_id), notes=d.notes,
            tracking_number=d.tracking_number, shipping_address=d.shipping_address,
            stock_request_id=d.stock_request_id, stock_request_number=sr_numbers.get(d.stock_request_id),
            delivered_on=d.delivered_on, delivery_reference=d.delivery_reference, receipt_notes=d.receipt_notes,
            shipping_method=d.shipping_method, carried_by_user_id=d.carried_by_user_id,
            carried_by=names.user_name(d.carried_by_user_id), note_emailed_at=d.note_emailed_at,
            note_email_to=d.note_email_to, note_email_error=d.note_email_error,
            received_by_name=d.received_by_name, photos=photos.get(d.id, []), photos_retired=retired.get(d.id, 0),
            lines=[DeliveryLineOut(
                id=ln.id, request_id=ln.request_id, request_number=req_numbers.get(ln.request_id),
                product_id=ln.product_id, sku=names.sku(ln.product_id), qty_dispatched=ln.qty_dispatched,
                qty_received=ln.qty_received, qty_returned=ln.qty_returned, qty_lost=ln.qty_lost,
                qty_late_received=ln.qty_late_received,
                qty_open=ln.qty_open if d.status != DeliveryStatus.IN_TRANSIT else ln.qty_dispatched,
            ) for ln in d.lines],
        )
        for d in deliveries
    ]


def names_for(db, d: Delivery) -> str:
    return Names(db).add("reseller", d.reseller_id).resolve().reseller_name(d.reseller_id) or f"the {vocab.partner}"


def _get_request(db, user: User, request_id: int) -> ReplenishmentRequest:
    r = db.get(ReplenishmentRequest, request_id)
    if r is None:
        raise NotFoundError("Replenishment request not found")
    ensure_reseller_access(user, r.reseller_id, "Replenishment request")
    return r


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


@router.get("/requests", response_model=list[RequestOut])
def list_requests(
    db: DB, user: Reader, status: Annotated[list[ReplenishmentStatus] | None, Query()] = None,
    reseller_id: int | None = None, location_id: int | None = None, product_id: int | None = None,
    reason: ReplenishmentReason | None = None, open_only: bool = False, backorders_only: bool = False,
    transfer_id: int | None = None, limit: Annotated[int, Query(ge=1, le=2000)] = 500,
):
    stmt = select(ReplenishmentRequest)
    restricted = scoped_reseller_id(user)
    if restricted is not None:
        stmt = stmt.where(ReplenishmentRequest.reseller_id == restricted)
    if status:
        stmt = stmt.where(ReplenishmentRequest.status.in_([s.value for s in status]))
    if open_only or backorders_only:
        stmt = stmt.where(ReplenishmentRequest.status.in_([s.value for s in OPEN_STATUSES]))
    if reseller_id is not None:
        stmt = stmt.where(ReplenishmentRequest.reseller_id == reseller_id)
    if location_id is not None:
        stmt = stmt.where(ReplenishmentRequest.location_id == location_id)
    if product_id is not None:
        stmt = stmt.where(ReplenishmentRequest.product_id == product_id)
    if reason is not None:
        stmt = stmt.where(ReplenishmentRequest.reason == reason)
    if transfer_id is not None:
        stmt = stmt.where(ReplenishmentRequest.transfer_id == transfer_id)
    rows = list(db.execute(stmt.order_by(ReplenishmentRequest.id.desc()).limit(limit)).scalars())
    if backorders_only:
        rows = [r for r in rows if r.qty_awaiting_supply > 0]
    return _for(user, requests_out(db, rows))


@router.get("/requests/{request_id}", response_model=RequestDetailOut)
def get_request(request_id: int, db: DB, user: Reader):
    r = _get_request(db, user, request_id)
    base = _for(user, requests_out(db, [r]))[0]
    events = db.execute(select(ReplenishmentEvent).where(ReplenishmentEvent.request_id == r.id)
                        .order_by(ReplenishmentEvent.id)).scalars().all()
    names = Names(db).add("user", *[e.actor_user_id for e in events]).resolve()
    allocs = db.execute(select(ReplenishmentAllocation).where(ReplenishmentAllocation.request_id == r.id)
                        .order_by(ReplenishmentAllocation.id)).scalars().all()
    dlines = db.execute(select(DeliveryLine, Delivery.number, Delivery.status)
                        .join(Delivery, Delivery.id == DeliveryLine.delivery_id)
                        .where(DeliveryLine.request_id == r.id).order_by(DeliveryLine.id)).all()
    deliveries = db.execute(select(Delivery).where(Delivery.id.in_({ln.delivery_id for ln, _, _ in dlines}))
                            .order_by(Delivery.id)).scalars().all() if dlines else []
    covering, fills = ([], None) if user.is_reseller_user else _transfer_chain(db, r)
    return RequestDetailOut(
        **base.model_dump(),
        covered_by_transfers=covering, fills_request=fills,
        events=_events_for(user, [
            EventOut(id=e.id, event_type=e.event_type, quantity=e.quantity, reference_type=e.reference_type,
                     reference_id=e.reference_id, reference_number=e.reference_number, reason=e.reason,
                     actor_name=names.user_name(e.actor_user_id), occurred_at=e.occurred_at) for e in events]),
        deliveries=deliveries_out(db, list(deliveries)),
        allocations=[AllocationOut(id=a.id, warehouse_location_id=a.warehouse_location_id, quantity=a.quantity,
                                   dispatched_qty=a.dispatched_qty, released_qty=a.released_qty, open_qty=a.open_qty,
                                   status=a.status, created_at=a.created_at) for a in allocs],
        delivery_lines=[{"delivery_id": ln.delivery_id, "delivery_number": num, "delivery_status": st,
                         "qty_dispatched": ln.qty_dispatched, "qty_received": ln.qty_received,
                         "qty_open": ln.qty_open if st != DeliveryStatus.IN_TRANSIT else ln.qty_dispatched}
                        for ln, num, st in dlines],
    )


def _transfer_chain(db, r: ReplenishmentRequest) -> tuple[list[CoveringTransferOut], LinkedRequestOut | None]:
    """Replenishment ↔ transfer ↔ the giving dealer's replacement, so each side shows the other."""
    from app.modules.transfers.models import Transfer  # transfers import this module

    def linked(req_id: int | None) -> LinkedRequestOut | None:
        req = db.get(ReplenishmentRequest, req_id) if req_id else None
        if req is None:
            return None
        return LinkedRequestOut(id=req.id, number=req.number, reseller_name=Names(db).add("reseller", req.reseller_id)
                                .resolve().reseller_name(req.reseller_id), status=req.status,
                                qty_awaiting_supply=req.qty_awaiting_supply)

    transfers = db.execute(select(Transfer).where(Transfer.destination_request_id == r.id).order_by(Transfer.id)).scalars().all()
    names = Names(db).add("reseller", *[t.source_reseller_id for t in transfers if t.source_reseller_id]).resolve()
    covering = [CoveringTransferOut(
        id=t.id, number=t.number, status=t.status, quantity=t.quantity,
        source_reseller_name=names.reseller_name(t.source_reseller_id) if t.source_reseller_id else None,
        replacement=linked(t.source_request_id)) for t in transfers]
    fills = None
    if r.reason == ReplenishmentReason.TRANSFER and r.transfer_id:
        origin = db.get(Transfer, r.transfer_id)
        fills = linked(origin.destination_request_id) if origin else None
    return covering, fills


@router.post("/requests", response_model=RequestOut, status_code=201)
def create_manual(data: ManualRequestIn, db: DB, user: Requester):
    r = service.create_manual(db, user, location_id=data.location_id, product_id=data.product_id,
                              qty=data.quantity, reason=data.reason, priority=data.priority,
                              expected_date=data.expected_date, approver_note=data.approver_note)
    db.commit()
    return _for(user, requests_out(db, [r]))[0]


@router.post("/generate-shortfalls", response_model=list[RequestOut])
def generate_shortfalls(data: GenerateShortfallsIn, db: DB, user: Manager):
    created = service.generate_shortfalls(db, user, reseller_id=data.reseller_id, location_id=data.location_id)
    db.commit()
    return requests_out(db, created)


@router.post("/requests/{request_id}/allocate", response_model=RequestOut)
def allocate(request_id: int, data: AllocateIn, db: DB, user: Manager):
    service.allocate(db, user, request_id, data.quantity, data.warehouse_location_id)
    db.commit()
    return requests_out(db, [db.get(ReplenishmentRequest, request_id)])[0]


@router.post("/requests/{request_id}/approve", response_model=RequestOut)
def approve(request_id: int, data: ApproveIn, db: DB, user: Approver):
    r = service.approve(db, user, request_id, data.approval, data.quantity, data.warehouse_location_id)
    db.commit()
    return requests_out(db, [r])[0]


@router.post("/requests/{request_id}/escalate", response_model=RequestOut)
def escalate(request_id: int, data: EscalateIn, db: DB, user: Approver):
    r = service.escalate(db, user, request_id, data.to_user_id, data.note)
    db.commit()
    return requests_out(db, [r])[0]


@router.post("/requests/{request_id}/hand-back", response_model=RequestOut)
def hand_back(request_id: int, data: HandBackIn, db: DB, user: Approver):
    r = service.hand_back(db, user, request_id, data.note)
    db.commit()
    return requests_out(db, [r])[0]


@router.post("/requests/{request_id}/reject", response_model=RequestOut)
def reject(request_id: int, data: RejectIn, db: DB, user: Approver):
    r = service.reject(db, user, request_id, data.reason)
    db.commit()
    return requests_out(db, [r])[0]


@router.post("/requests/{request_id}/ready", response_model=RequestOut)
def ready(request_id: int, db: DB, user: Dispatcher):
    r = service.mark_ready(db, user, request_id)
    db.commit()
    return requests_out(db, [r])[0]


@router.post("/requests/{request_id}/ship", response_model=DeliveryOut, status_code=201)
def ship(request_id: int, data: ShipIn, db: DB, user: Dispatcher):
    d = service.ship(db, user, request_id, shipping_method=data.shipping_method, carrier=data.carrier,
                     tracking_number=data.tracking_number, carried_by_user_id=data.carried_by_user_id,
                     notes=data.notes, qty=data.quantity)
    db.commit()
    return deliveries_out(db, [d])[0]


@router.post("/allocations/{allocation_id}/release", response_model=RequestOut)
def release(allocation_id: int, data: ReleaseIn, db: DB, user: Manager):
    alloc = db.get(ReplenishmentAllocation, allocation_id)
    if alloc is None:
        raise NotFoundError("Allocation not found")
    service.release_allocation(db, user.id, allocation_id, data.reason)
    db.commit()
    return requests_out(db, [db.get(ReplenishmentRequest, alloc.request_id)])[0]


@router.post("/requests/{request_id}/cancel", response_model=RequestOut)
def cancel(request_id: int, data: CancelIn, db: DB, user: Annotated[User, Depends(require(P.REPLENISHMENT_CANCEL))]):
    r = service.cancel(db, user, request_id, data.quantity, data.reason)
    db.commit()
    return requests_out(db, [r])[0]


@router.post("/requests/{request_id}/planning", response_model=RequestOut)
def planning(request_id: int, data: PlanningIn, db: DB, user: Manager):
    r = service.update_planning(db, user, request_id, reason=data.reason, priority=data.priority,
                                expected_date=data.expected_date, clear_expected_date=data.clear_expected_date,
                                purchase_order_line_id=data.purchase_order_line_id)
    db.commit()
    return requests_out(db, [r])[0]


@router.get("/coverage", response_model=CoverageOut)
def coverage(location_id: int, product_id: int, db: DB, user: Reader):
    from app.modules.customers.service import get_location_scoped

    get_location_scoped(db, user, location_id)
    c = service.coverage(db, location_id, product_id)
    return CoverageOut(location_id=location_id, product_id=product_id, target=c.target,
                       auto_replenish=c.auto_replenish, on_hand=c.on_hand, open_outstanding=c.open_outstanding,
                       in_transit_replenishment=c.in_transit_replenishment, inbound_transfers=c.inbound_transfers,
                       shortfall=c.shortfall)


# ---------------------------------------------------------------------------
# Allocation proposals (after goods receipt)
# ---------------------------------------------------------------------------


@router.get("/allocation-proposal", response_model=list[ProposalOut])
def proposal(db: DB, user: Manager, warehouse_location_id: int | None = None, product_id: int | None = None):
    props = service.allocation_proposal(db, warehouse_location_id=warehouse_location_id, product_id=product_id)
    names = Names(db)
    for p in props:
        names.add("reseller", p.reseller_id).add("location", p.location_id).add("product", p.product_id)
    names.resolve()
    return [ProposalOut(**p.__dict__, reseller_name=names.reseller_name(p.reseller_id),
                        location_code=names.loc_code(p.location_id), sku=names.sku(p.product_id)) for p in props]


@router.post("/allocation-proposal/confirm", response_model=list[RequestOut])
def confirm(data: ConfirmAllocationsIn, db: DB, user: Manager):
    allocs = service.confirm_allocations(db, user, [(ln.request_id, ln.quantity) for ln in data.lines],
                                         data.warehouse_location_id)
    db.commit()
    return requests_out(db, [db.get(ReplenishmentRequest, a.request_id) for a in allocs])


# ---------------------------------------------------------------------------
# Dispatch & deliveries
# ---------------------------------------------------------------------------


class PickRow(BaseModel):
    allocation_id: int
    request_id: int
    request_number: str
    reseller_id: int
    reseller_name: str | None
    location_id: int
    location_code: str | None
    product_id: int
    sku: str | None
    product_name: str | None
    warehouse_location_id: int
    open_qty: int
    priority: str
    ready: bool = False   # picked and packed on the request (1.11)


@router.get("/pick-list", response_model=list[PickRow])
def pick_list(db: DB, user: Annotated[User, Depends(require(P.DISPATCH))]):
    rows = db.execute(
        select(ReplenishmentAllocation, ReplenishmentRequest)
        .join(ReplenishmentRequest, ReplenishmentRequest.id == ReplenishmentAllocation.request_id)
        .where(ReplenishmentAllocation.status == AllocationStatus.ACTIVE)
        .order_by(ReplenishmentRequest.location_id, ReplenishmentRequest.id)
    ).tuples().all()
    names = Names(db)
    for _, r in rows:
        names.add("reseller", r.reseller_id).add("location", r.location_id).add("product", r.product_id)
    names.resolve()
    return [PickRow(allocation_id=a.id, request_id=r.id, request_number=r.number, reseller_id=r.reseller_id,
                    reseller_name=names.reseller_name(r.reseller_id), location_id=r.location_id,
                    location_code=names.loc_code(r.location_id), product_id=r.product_id, sku=names.sku(r.product_id),
                    product_name=names.product_name(r.product_id), warehouse_location_id=a.warehouse_location_id,
                    open_qty=a.open_qty, priority=r.priority, ready=r.ready_at is not None) for a, r in rows]


@router.get("/deliveries", response_model=list[DeliveryOut])
def list_deliveries(db: DB, user: Reader, status: DeliveryStatus | None = None, reseller_id: int | None = None,
                    open_only: bool = False, limit: Annotated[int, Query(ge=1, le=1000)] = 200):
    stmt = select(Delivery)
    restricted = scoped_reseller_id(user)
    if restricted is not None:
        stmt = stmt.where(Delivery.reseller_id == restricted)
    if status is not None:
        stmt = stmt.where(Delivery.status == status)
    if open_only:
        stmt = stmt.where(Delivery.status.in_([DeliveryStatus.IN_TRANSIT.value,
                                               DeliveryStatus.RECEIVED_WITH_DISCREPANCY.value]))
    if reseller_id is not None:
        stmt = stmt.where(Delivery.reseller_id == reseller_id)
    return deliveries_out(db, list(db.execute(stmt.order_by(Delivery.id.desc()).limit(limit)).scalars()))


@router.get("/deliveries/{delivery_id}", response_model=DeliveryOut)
def get_delivery(delivery_id: int, db: DB, user: Reader):
    d = db.get(Delivery, delivery_id)
    if d is None:
        raise NotFoundError("Delivery not found")
    ensure_reseller_access(user, d.reseller_id, "Delivery")
    return deliveries_out(db, [d])[0]


@router.post("/deliveries", response_model=DeliveryOut, status_code=201)
def dispatch(data: DispatchIn, db: DB, user: Annotated[User, Depends(require(P.DISPATCH))]):
    d = service.dispatch(db, user, to_location_id=data.to_location_id,
                         lines=[(ln.request_id, ln.quantity) for ln in data.lines],
                         carrier_reference=data.carrier_reference, notes=data.notes,
                         tracking_number=data.tracking_number, shipping_address=data.shipping_address,
                         shipping_method=data.shipping_method, carried_by_user_id=data.carried_by_user_id)
    if d.carried_by_user_id:
        notify_users(db, [d.carried_by_user_id], f"Please deliver {d.number}",
                     f"{sum(ln.qty_dispatched for ln in d.lines)} unit(s) to {names_for(db, d)}. "
                     "Confirm delivery on arrival.", link="/replenishment?tab=deliveries", entity_type="delivery",
                     entity_id=d.id, exclude=user.id)
    db.commit()
    return deliveries_out(db, [d])[0]


@router.post("/deliveries/{delivery_id}/receive", response_model=DeliveryOut)
def receive(delivery_id: int, data: ReceiveIn, db: DB, user: Annotated[User, Depends(require(P.DELIVERY_CONFIRM))]):
    service.receive_delivery(db, user, delivery_id, {ln.line_id: ln.qty_received for ln in data.lines}, data.notes,
                             data.delivered_on, data.delivery_reference, data.received_by_name, data.photos)
    db.commit()
    delivery_notes.send_after_receipt(db, delivery_id)
    return deliveries_out(db, [db.get(Delivery, delivery_id)])[0]


@router.get("/deliveries/{delivery_id}/delivery-note.pdf")
def delivery_note_pdf(delivery_id: int, db: DB, user: Reader):
    d = db.get(Delivery, delivery_id)
    if d is None:
        raise NotFoundError("Delivery not found")
    ensure_reseller_access(user, d.reseller_id, "Delivery")
    pdf = delivery_notes.render_pdf(delivery_notes.note_data(db, d))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="Delivery-note-{d.number}.pdf"'})


@router.post("/deliveries/{delivery_id}/email-delivery-note")
def email_delivery_note(delivery_id: int, db: DB, user: Manager):
    """Send (or resend) the delivery note to the reseller's email address."""
    d = db.get(Delivery, delivery_id)
    if d is None:
        raise NotFoundError("Delivery not found")
    if d.received_at is None:
        raise BusinessRuleError("The delivery note is emailed once the delivery has been confirmed")
    status = delivery_notes.send(db, d)
    db.commit()
    return {"status": status, "delivery": deliveries_out(db, [d])[0]}


@router.post("/deliveries/{delivery_id}/resolve", response_model=DeliveryOut)
def resolve(delivery_id: int, data: ResolveIn, db: DB, user: Manager):
    d = service.resolve_delivery_line(db, user, delivery_id, data.line_id, data.outcome, data.quantity, data.reason)
    db.commit()
    return deliveries_out(db, [d])[0]
