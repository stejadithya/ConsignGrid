from collections import defaultdict
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, update

from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.lookups import Names
from app.core.messages import KIND_REJECTION, NOT_AVAILABLE_LABEL
from app.core.permissions import P
from app.modules.catalogue.models import Product
from app.modules.customers.models import Location, LocationType
from app.modules.delivery_notes import service as delivery_notes
from app.modules.identity.deps import DB, CurrentUser, require
from app.modules.identity.models import User
from app.modules.identity.scoping import scoped_reseller_id
from app.modules.inventory import availability
from app.modules.inventory.models import StockBalance
from app.modules.inventory.service import default_warehouse, get_balance
from app.modules.replenishment.models import AllocationStatus, Delivery, ReplenishmentAllocation, ReplenishmentRequest
from app.modules.replenishment.router import deliveries_out
from app.modules.stock_requests import service
from app.modules.stock_requests.models import (
    PENDING_STATUSES,
    Notification,
    StockRequest,
    StockRequestEvent,
    StockRequestLine,
)
from app.modules.stock_requests.models import StockRequestStatus as S
from app.modules.stock_requests.schemas import (
    AllocationRow,
    CallbackIn,
    ConfirmDeliveryIn,
    DecisionIn,
    EscalateIn,
    EventOut,
    HandBackIn,
    InventoryRow,
    LineOut,
    NotificationOut,
    ReasonIn,
    ReleaseIn,
    ReserveIn,
    ShipIn,
    StockRequestDetailOut,
    StockRequestIn,
    StockRequestOut,
    StockRequestUpdate,
    SupplyCheckIn,
    SupplyCheckOut,
)
from app.modules.stock_requests.schemas import LineIn as LineSchema
from app.modules.stocktakes import service as stocktakes
from app.modules.transfers.models import Transfer

router = APIRouter(prefix="/stock-requests", tags=["stock requests"])
notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])

Reader = Annotated[User, Depends(require(P.STOCK_REQUEST_READ))]
Creator = Annotated[User, Depends(require(P.STOCK_REQUEST_CREATE))]
Approver = Annotated[User, Depends(require(P.STOCK_REQUEST_APPROVE))]
Fulfiller = Annotated[User, Depends(require(P.STOCK_REQUEST_FULFIL))]
StockReader = Annotated[User, Depends(require(P.INVENTORY_READ))]

VIEWS = {
    "pending": PENDING_STATUSES,
    "approved": (S.APPROVED, S.PARTIALLY_APPROVED, S.READY_FOR_SHIPMENT),   # open ones only, see list_requests
    "shipments": (S.READY_FOR_SHIPMENT, S.SHIPPED, S.DELIVERED),
}


def _lines_in(lines: list[LineSchema]) -> list[service.LineIn]:
    return [service.LineIn(ln.product_id, ln.quantity, ln.notes, ln.find_for_me) for ln in lines]


def _visible(stmt, user: User):
    """Reseller users see their own reseller only; nobody sees someone else's unsubmitted draft."""
    restricted = scoped_reseller_id(user)
    if restricted is not None:
        return stmt.where(StockRequest.reseller_id == restricted)
    return stmt.where(or_(StockRequest.status != S.DRAFT, StockRequest.created_by_user_id == user.id))


def requests_out(db, rows: list[StockRequest]) -> list[StockRequestOut]:
    names = Names(db)
    for sr in rows:
        names.add("reseller", sr.reseller_id).add("location", sr.location_id)
        names.add("user", sr.created_by_user_id, sr.reviewed_by_user_id, sr.escalated_to_user_id, sr.escalated_by_user_id)
    names.resolve()
    rep_ids = [ln.replenishment_request_id for sr in rows for ln in sr.lines if ln.replenishment_request_id]
    reqs = {r.id: r for r in db.execute(select(ReplenishmentRequest).where(ReplenishmentRequest.id.in_(rep_ids)))
            .scalars()} if rep_ids else {}
    out = []
    for sr in rows:
        linked = [reqs[ln.replenishment_request_id] for ln in sr.lines if ln.replenishment_request_id in reqs]
        out.append(StockRequestOut(
            id=sr.id, number=sr.number, reseller_id=sr.reseller_id, reseller_name=names.reseller_name(sr.reseller_id),
            location_id=sr.location_id, location_code=names.loc_code(sr.location_id), status=sr.status,
            decision=sr.decision, priority=sr.priority, required_date=sr.required_date, notes=sr.notes,
            shipping_address=sr.shipping_address, created_by=names.user_name(sr.created_by_user_id),
            created_by_user_id=sr.created_by_user_id, created_by_role=sr.created_by_role, created_at=sr.created_at,
            submitted_at=sr.submitted_at, reviewed_by=names.user_name(sr.reviewed_by_user_id),
            reviewed_by_role=sr.reviewed_by_role, reviewed_at=sr.reviewed_at, review_notes=sr.review_notes,
            ready_at=sr.ready_at, closed_at=sr.closed_at, line_count=len(sr.lines),
            qty_requested=sum(ln.qty_requested for ln in sr.lines),
            qty_approved=sum(ln.qty_approved for ln in sr.lines),
            qty_rejected=sum(ln.qty_rejected for ln in sr.lines),
            qty_backordered=sum(ln.qty_backordered for ln in sr.lines),
            qty_reserved=sum(r.qty_allocated for r in linked),
            qty_shipped=sum(r.qty_in_transit + r.qty_delivered for r in linked),
            qty_delivered=sum(r.qty_delivered for r in linked),
            escalated_to_user_id=sr.escalated_to_user_id, escalated_to=names.user_name(sr.escalated_to_user_id),
            escalated_by=names.user_name(sr.escalated_by_user_id), escalated_at=sr.escalated_at,
            escalation_note=sr.escalation_note,
        ))
    return out


_STAFF_ONLY = ("escalated_to_user_id", "escalated_to", "escalated_by", "escalated_at", "escalation_note")


def _for(user: User, rows: list):
    """Hide internal workflow details (who it was escalated to, notes) from dealer users. Where anything was not
    supplied, a dealer sees the standard kind message instead of the internal reason (D5)."""
    if scoped_reseller_id(user) is not None:
        for r in rows:
            for k in _STAFF_ONLY:
                setattr(r, k, None)
            r.review_notes = KIND_REJECTION if r.qty_rejected else None
    return rows


_DECISION_EVENTS = {"APPROVED", "PARTIALLY_APPROVED", "REJECTED"}
_STAFF_EVENTS = {"ESCALATED", "HANDED_BACK", "REVIEW_STARTED"}


def _dealer_event_summary(e: StockRequestEvent) -> str:
    d = e.details or {}
    approved, backordered, rejected = d.get("approved", 0), d.get("backordered", 0), d.get("rejected", 0)
    parts = [f"{approved} approved"] if approved else []
    if backordered:
        parts.append(f"{backordered} to follow when stock arrives")
    if rejected:
        parts.append(f"{rejected} {NOT_AVAILABLE_LABEL.lower()}")
    head = "Your order was reviewed" + (f": {', '.join(parts)}" if parts else "")
    return head + (f". {KIND_REJECTION}" if rejected else "")


def detail_out(db, user: User, sr: StockRequest) -> StockRequestDetailOut:
    base = _for(user, requests_out(db, [sr]))[0]
    names = Names(db).add("product", *[ln.product_id for ln in sr.lines])
    events = db.execute(select(StockRequestEvent).where(StockRequestEvent.stock_request_id == sr.id)
                        .order_by(StockRequestEvent.id)).scalars().all()
    names.add("user", *[e.actor_user_id for e in events]).resolve()
    fil = service.fulfilment(db, sr)
    first = dict(db.execute(select(ReplenishmentRequest.id, ReplenishmentRequest.first_supply).where(
        ReplenishmentRequest.id.in_([ln.replenishment_request_id for ln in sr.lines if ln.replenishment_request_id]),
    )).all())
    rep_numbers = dict(db.execute(select(ReplenishmentRequest.id, ReplenishmentRequest.number).where(
        ReplenishmentRequest.id.in_([ln.replenishment_request_id for ln in sr.lines if ln.replenishment_request_id]),
    )).all())
    show_stock = scoped_reseller_id(user) is None   # warehouse availability is for dealership staff only
    warehouse = default_warehouse(db) if show_stock else None
    holdings = availability.dealer_holdings(db, sr.location_id, [ln.product_id for ln in sr.lines]) if show_stock else {}
    shipments = db.execute(select(Delivery).where(Delivery.stock_request_id == sr.id).order_by(Delivery.id)).scalars()
    transfer_ids = [ln.arranging_transfer_id for ln in sr.lines if ln.arranging_transfer_id]
    transfer_numbers = dict(db.execute(select(Transfer.id, Transfer.number).where(Transfer.id.in_(transfer_ids)))
                            .all()) if transfer_ids else {}
    req_ids = [ln.replenishment_request_id for ln in sr.lines if ln.replenishment_request_id]
    covering: dict[int, list[dict]] = {}
    if show_stock and req_ids:
        for t in db.execute(select(Transfer).where(Transfer.destination_request_id.in_(req_ids),
                                                   Transfer.status.not_in(("CANCELLED", "REJECTED")))
                            .order_by(Transfer.id)).scalars():
            covering.setdefault(t.destination_request_id, []).append(
                {"id": t.id, "number": t.number, "status": t.status, "quantity": t.quantity})
    return StockRequestDetailOut(
        **base.model_dump(),
        lines=[LineOut(
            id=ln.id, line_no=ln.line_no, product_id=ln.product_id, sku=names.sku(ln.product_id),
            product_name=names.product_name(ln.product_id),
            product_active=bool(names.products.get(ln.product_id) and names.products[ln.product_id].is_active),
            qty_requested=ln.qty_requested, qty_approved=ln.qty_approved, qty_rejected=ln.qty_rejected,
            qty_backordered=ln.qty_backordered, qty_released=ln.qty_released, qty_reserved=fil[ln.id].reserved,
            qty_in_transit=fil[ln.id].in_transit, qty_shipped=fil[ln.id].shipped, qty_delivered=fil[ln.id].delivered,
            qty_backorder_open=fil[ln.id].backorder_open, notes=ln.notes,
            decision_notes=ln.decision_notes if show_stock else (KIND_REJECTION if ln.qty_rejected else None),
            replenishment_request_id=ln.replenishment_request_id,
            replenishment_number=rep_numbers.get(ln.replenishment_request_id),
            warehouse_available=get_balance(db, warehouse.id, ln.product_id).available if warehouse else None,
            first_supply=bool(first.get(ln.replenishment_request_id)),
            find_for_me=ln.find_for_me, qty_arranging=ln.qty_arranging, arranging_transfer_id=ln.arranging_transfer_id,
            arranging_transfer_number=transfer_numbers.get(ln.arranging_transfer_id),
            dealer_on_hand=holdings[ln.product_id][0] if show_stock else None,
            dealer_on_hand_all=holdings[ln.product_id][1] if show_stock else None,
            covering_transfers=covering.get(ln.replenishment_request_id, []),
        ) for ln in sr.lines],
        events=[EventOut(id=e.id, action=e.action, from_status=e.from_status, to_status=e.to_status,
                         summary=e.summary if show_stock or e.action not in _DECISION_EVENTS else _dealer_event_summary(e),
                         details=e.details if show_stock else None, actor_name=names.user_name(e.actor_user_id),
                         actor_role=e.actor_role, occurred_at=e.occurred_at)
                for e in events if show_stock or e.action not in _STAFF_EVENTS],
        shipments=deliveries_out(db, list(shipments)),
        approval_method=sr.approval_method if show_stock else None,
        approval_contact=sr.approval_contact if show_stock else None,
        approval_comments=sr.approval_comments if show_stock else None,
    )


def _detail(db, user: User, request_id: int) -> StockRequestDetailOut:
    db.expire_all()
    return detail_out(db, user, service.get_scoped(db, user, request_id))


# ---------------------------------------------------------------------------
# Inventory views (static paths first so they are not taken for a request id)
# ---------------------------------------------------------------------------


@router.get("/inventory/overview", response_model=list[InventoryRow])
def inventory_overview(db: DB, user: StockReader):
    """Per SKU: Total = warehouse on hand + shipped (in transit); Available = Total − Reserved − Shipped − Blocked."""
    if scoped_reseller_id(user) is not None:
        raise PermissionDeniedError("Warehouse stock is visible to staff only")
    sums: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    rows = db.execute(
        select(StockBalance.product_id, Location.type, func.sum(StockBalance.on_hand), func.sum(StockBalance.reserved),
               func.sum(StockBalance.blocked))
        .join(Location, Location.id == StockBalance.location_id)
        .where(Location.type.in_([LocationType.WAREHOUSE.value, LocationType.TRANSIT.value,
                                  LocationType.CONSIGNMENT.value]))
        .group_by(StockBalance.product_id, Location.type)
    ).all()
    for pid, loc_type, on_hand, reserved, blocked in rows:
        s = sums[pid]
        if loc_type == LocationType.WAREHOUSE:
            s["on_hand"] += int(on_hand)
            s["reserved"] += int(reserved)
            s["blocked"] += int(blocked)
        elif loc_type == LocationType.TRANSIT:
            s["shipped"] += int(on_hand)
        else:
            s["delivered"] += int(on_hand)
    pending = dict(db.execute(
        select(StockRequestLine.product_id, func.sum(StockRequestLine.qty_requested))
        .join(StockRequest, StockRequest.id == StockRequestLine.stock_request_id)
        .where(StockRequest.status.in_([s.value for s in PENDING_STATUSES]))
        .group_by(StockRequestLine.product_id)
    ).all())
    products = db.execute(select(Product).order_by(Product.brand, Product.sku)).scalars()
    out = []
    for p in products:
        s = sums.get(p.id, {})
        if not p.is_active and not any(s.values()):
            continue
        on_hand, shipped = s.get("on_hand", 0), s.get("shipped", 0)
        out.append(InventoryRow(
            product_id=p.id, sku=p.sku, product_name=p.display_name, is_active=p.is_active, warehouse_on_hand=on_hand,
            blocked=s.get("blocked", 0), reserved=s.get("reserved", 0), shipped=shipped, total=on_hand + shipped,
            available=on_hand - s.get("reserved", 0) - s.get("blocked", 0), delivered=s.get("delivered", 0),
            requested_pending=int(pending.get(p.id, 0)),
        ))
    return out


@router.get("/inventory/allocations", response_model=list[AllocationRow])
def inventory_allocations(db: DB, user: StockReader, product_id: int | None = None):
    """Warehouse stock currently reserved for resellers (approved but not yet shipped)."""
    stmt = (select(ReplenishmentAllocation, ReplenishmentRequest)
            .join(ReplenishmentRequest, ReplenishmentRequest.id == ReplenishmentAllocation.request_id)
            .where(ReplenishmentAllocation.status == AllocationStatus.ACTIVE)
            .order_by(ReplenishmentRequest.product_id, ReplenishmentAllocation.id))
    restricted = scoped_reseller_id(user)
    if restricted is not None:
        stmt = stmt.where(ReplenishmentRequest.reseller_id == restricted)
    if product_id is not None:
        stmt = stmt.where(ReplenishmentRequest.product_id == product_id)
    rows = db.execute(stmt).tuples().all()
    req_ids = [r.id for _, r in rows]
    srs = dict(db.execute(
        select(StockRequestLine.replenishment_request_id, StockRequest)
        .join(StockRequest, StockRequest.id == StockRequestLine.stock_request_id)
        .where(StockRequestLine.replenishment_request_id.in_(req_ids))
    ).tuples().all()) if req_ids else {}
    names = Names(db)
    for _, r in rows:
        names.add("product", r.product_id).add("reseller", r.reseller_id).add("location", r.location_id)
    names.resolve()
    return [AllocationRow(
        allocation_id=a.id, product_id=r.product_id, sku=names.sku(r.product_id),
        product_name=names.product_name(r.product_id), reseller_id=r.reseller_id,
        reseller_name=names.reseller_name(r.reseller_id), location_code=names.loc_code(r.location_id),
        quantity=a.quantity, open_qty=a.open_qty, replenishment_request_id=r.id, replenishment_number=r.number,
        stock_request_id=srs[r.id].id if r.id in srs else None,
        stock_request_number=srs[r.id].number if r.id in srs else None, created_at=a.created_at,
    ) for a, r in rows if a.open_qty > 0]


@router.get("/summary")
def summary(db: DB, user: Reader):
    """Counts by status for dashboards (same visibility as the list)."""
    stmt = _visible(select(StockRequest.status, func.count()).group_by(StockRequest.status), user)
    counts = {s.value: 0 for s in S}
    for status, n in db.execute(stmt).all():
        counts[status.value if hasattr(status, "value") else status] = n
    mine = db.execute(_visible(select(func.count()).select_from(StockRequest), user)
                      .where(StockRequest.created_by_user_id == user.id,
                             StockRequest.status.not_in([S.DELIVERED.value, S.REJECTED.value, S.CANCELLED.value]))
                      ).scalar_one()
    return {"by_status": counts, "pending_approval": counts["SUBMITTED"] + counts["UNDER_REVIEW"],
            "to_ship": counts["APPROVED"] + counts["PARTIALLY_APPROVED"] + counts["READY_FOR_SHIPMENT"],
            "in_transit": counts["SHIPPED"], "my_open": mine}


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


@router.get("", response_model=list[StockRequestOut])
def list_requests(
    db: DB, user: Reader, view: Literal["all", "mine", "pending", "approved", "shipments"] = "all",
    status: Annotated[list[S] | None, Query()] = None, reseller_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 300,
):
    stmt = _visible(select(StockRequest), user)
    if view == "mine" and scoped_reseller_id(user) is None:
        stmt = stmt.where(StockRequest.created_by_user_id == user.id)
    elif view in VIEWS:
        stmt = stmt.where(StockRequest.status.in_([s.value for s in VIEWS[view]]))
        if view == "approved":   # a request the warehouse is arranging entirely has nothing to pick
            stmt = stmt.where(StockRequest.closed_at.is_(None))
    if status:
        stmt = stmt.where(StockRequest.status.in_([s.value for s in status]))
    if reseller_id is not None:
        stmt = stmt.where(StockRequest.reseller_id == reseller_id)
    rows = list(db.execute(stmt.order_by(StockRequest.id.desc()).limit(limit)).scalars())
    return _for(user, requests_out(db, rows))


@router.post("/supply-check", response_model=list[SupplyCheckOut])
def supply_check(data: SupplyCheckIn, db: DB, user: Creator):
    """Whether the warehouse can cover each line right now. Says only yes / no, never how many are in stock."""
    return service.supply_check(db, [(ln.product_id, ln.quantity) for ln in data.lines])


@router.post("", response_model=StockRequestDetailOut, status_code=201)
def create(data: StockRequestIn, db: DB, user: Creator):
    sr = service.create(db, user, location_id=data.location_id, lines=_lines_in(data.lines), priority=data.priority,
                        required_date=data.required_date, notes=data.notes, shipping_address=data.shipping_address,
                        submit_now=data.submit)
    db.commit()
    return _detail(db, user, sr.id)


@router.get("/{request_id}", response_model=StockRequestDetailOut)
def get_request(request_id: int, db: DB, user: Reader):
    sr = service.get_scoped(db, user, request_id)
    if sr.status == S.DRAFT and scoped_reseller_id(user) is None and sr.created_by_user_id != user.id:
        raise NotFoundError("Stock request not found")
    return detail_out(db, user, sr)


@router.put("/{request_id}", response_model=StockRequestDetailOut)
def update_draft(request_id: int, data: StockRequestUpdate, db: DB, user: Creator):
    service.update_draft(db, user, request_id, lines=_lines_in(data.lines), priority=data.priority,
                         required_date=data.required_date, notes=data.notes, shipping_address=data.shipping_address)
    db.commit()
    return _detail(db, user, request_id)


@router.post("/{request_id}/submit", response_model=StockRequestDetailOut)
def submit(request_id: int, db: DB, user: Creator):
    service.submit(db, user, request_id)
    db.commit()
    return _detail(db, user, request_id)


@router.post("/{request_id}/cancel", response_model=StockRequestDetailOut)
def cancel(request_id: int, data: ReasonIn, db: DB, user: Reader):
    service.cancel(db, user, request_id, data.reason)
    db.commit()
    return _detail(db, user, request_id)


@router.post("/{request_id}/review", response_model=StockRequestDetailOut)
def start_review(request_id: int, db: DB, user: Approver):
    service.start_review(db, user, request_id)
    db.commit()
    return _detail(db, user, request_id)


@router.post("/{request_id}/decision", response_model=StockRequestDetailOut)
def decide(request_id: int, data: DecisionIn, db: DB, user: Approver):
    service.decide(db, user, request_id, [service.Decision(d.line_id, d.approve_qty, d.remainder, d.notes)
                                          for d in data.lines], data.notes, data.approval)
    db.commit()
    return _detail(db, user, request_id)


@router.post("/{request_id}/escalate", response_model=StockRequestDetailOut)
def escalate(request_id: int, data: EscalateIn, db: DB, user: Approver):
    """Send to a Relationship Manager for approval (D10); while it waits only they or an Administrator can decide."""
    service.escalate(db, user, request_id, data.to_user_id, data.note)
    db.commit()
    return _detail(db, user, request_id)


@router.post("/{request_id}/callback", response_model=StockRequestDetailOut)
def request_callback(request_id: int, data: CallbackIn, db: DB, user: Reader):
    """'Please call me': notifies the Relationship Managers and the dealer's sales rep."""
    service.request_callback(db, user, request_id, data.preferred_time, data.phone)
    db.commit()
    return _detail(db, user, request_id)


@router.post("/{request_id}/hand-back", response_model=StockRequestDetailOut)
def hand_back(request_id: int, data: HandBackIn, db: DB, user: Approver):
    service.hand_back(db, user, request_id, data.note)
    db.commit()
    return _detail(db, user, request_id)


@router.post("/{request_id}/reject", response_model=StockRequestDetailOut)
def reject(request_id: int, data: ReasonIn, db: DB, user: Approver):
    service.reject(db, user, request_id, data.reason)
    db.commit()
    return _detail(db, user, request_id)


@router.post("/{request_id}/lines/{line_id}/reserve", response_model=StockRequestDetailOut)
def reserve(request_id: int, line_id: int, data: ReserveIn, db: DB, user: Approver):
    service.reserve_backorder(db, user, request_id, line_id, data.quantity)
    db.commit()
    return _detail(db, user, request_id)


@router.post("/{request_id}/lines/{line_id}/release", response_model=StockRequestDetailOut)
def release(request_id: int, line_id: int, data: ReleaseIn, db: DB, user: Approver):
    service.release(db, user, request_id, line_id, data.reason, data.to_backorder)
    db.commit()
    return _detail(db, user, request_id)


@router.post("/{request_id}/ready", response_model=StockRequestDetailOut)
def mark_ready(request_id: int, db: DB, user: Fulfiller):
    service.mark_ready(db, user, request_id)
    db.commit()
    return _detail(db, user, request_id)


@router.post("/{request_id}/ship", response_model=StockRequestDetailOut)
def ship(request_id: int, data: ShipIn, db: DB, user: Fulfiller):
    service.ship(db, user, request_id, carrier=data.carrier, shipping_method=data.shipping_method,
                 carried_by_user_id=data.carried_by_user_id, tracking_number=data.tracking_number,
                 shipping_address=data.shipping_address, notes=data.notes,
                 quantities=None if data.lines is None else {ln.line_id: ln.quantity for ln in data.lines})
    db.commit()
    return _detail(db, user, request_id)


@router.post("/{request_id}/shipments/{delivery_id}/confirm", response_model=StockRequestDetailOut)
def confirm_delivery(request_id: int, delivery_id: int, data: ConfirmDeliveryIn, db: DB,
                     user: Annotated[User, Depends(require(P.DELIVERY_CONFIRM))]):
    service.confirm_delivery(db, user, request_id, delivery_id,
                             received={ln.line_id: ln.qty_received for ln in data.lines},
                             delivered_on=data.delivered_on, reference=data.reference, notes=data.notes,
                             received_by_name=data.received_by_name, photos=data.photos)
    db.commit()
    delivery_notes.send_after_receipt(db, delivery_id)
    return _detail(db, user, request_id)


# ---------------------------------------------------------------------------
# Notifications (every signed-in user sees only their own)
# ---------------------------------------------------------------------------


@notifications_router.get("", response_model=list[NotificationOut])
def my_notifications(db: DB, user: CurrentUser, unread_only: bool = False,
                     limit: Annotated[int, Query(ge=1, le=200)] = 30,
                     after_id: Annotated[int | None, Query(ge=0)] = None):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    if after_id is not None:   # only notifications newer than the last one the client has seen
        stmt = stmt.where(Notification.id > after_id)
    return list(db.execute(stmt.order_by(Notification.id.desc()).limit(limit)).scalars())


@notifications_router.get("/unread-count")
def unread_count(db: DB, user: CurrentUser):
    # Stock-check reminders and the end of the find window are handled here (the bell polls every 20 seconds), so no
    # scheduler is needed; a daily cron does the same (/api/stocktakes/auto-invoice/cron).
    if stocktakes.auto_invoice_due(db) + stocktakes.send_due_reminders(db):
        db.commit()
    n = db.execute(select(func.count()).select_from(Notification)
                   .where(Notification.user_id == user.id, Notification.read_at.is_(None))).scalar_one()
    latest = db.execute(select(func.max(Notification.id)).where(Notification.user_id == user.id)).scalar_one()
    return {"unread": n, "latest_id": latest or 0}


@notifications_router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, db: DB, user: CurrentUser):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise NotFoundError("Notification not found")
    if n.read_at is None:
        n.read_at = datetime.now(UTC)
        db.commit()
    return n


@notifications_router.post("/read-all")
def mark_all_read(db: DB, user: CurrentUser):
    result = db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
                        .values(read_at=datetime.now(UTC)))
    db.commit()
    return {"marked": result.rowcount}



