"""Consignment stock requests: draft → submitted → under review → approved / partially approved / rejected
→ ready for shipment → shipped → delivered.

Approval turns each approved line into one replenishment request (reason STOCK_REQUEST): the approved quantity
is reserved in the warehouse immediately (so it cannot be allocated twice) and any backordered remainder waits
for supply exactly like other backorders. Shipment and delivery reuse replenishment dispatch / receipt, so the
inventory ledger stays the single source of truth. See docs/STOCK_REQUESTS.md.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.messages import KIND_REJECTION
from app.core.numbering import next_number
from app.core.permissions import P, Role, role_has
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product
from app.modules.customers.models import Location, LocationType, Reseller, ResellerStatus
from app.modules.identity.models import User
from app.modules.identity.scoping import ensure_reseller_access
from app.modules.inventory.models import StockBalance
from app.modules.inventory.service import Ref, default_warehouse, get_balance
from app.modules.notifications.service import notify_users, reseller_users, staff_in_roles, staff_with
from app.modules.replenishment import service as replenishment
from app.modules.replenishment.models import (
    AllocationStatus,
    Delivery,
    Priority,
    ReplenishmentAllocation,
    ReplenishmentReason,
    ReplenishmentRequest,
)
from app.modules.stock_requests.models import (
    FULFILMENT_STATUSES,
    PENDING_STATUSES,
    RemainderAction,
    StockRequest,
    StockRequestEvent,
    StockRequestLine,
)
from app.modules.stock_requests.models import StockRequestStatus as S

_QUIET = "stock_request_quiet"  # session.info key: requests whose status changes are being recorded by the caller


def _now() -> datetime:
    return datetime.now(UTC)


def _role(user: User | None) -> str | None:
    return Role(user.role).value if user is not None else None


def _require(user: User, perm: P) -> None:
    if not role_has(user.role, perm):
        raise PermissionDeniedError(f"Missing permission: {perm.value}")


def link(sr: StockRequest) -> str:
    return f"/stock-requests/{sr.id}"


# ---------------------------------------------------------------------------
# Loading, history and notifications
# ---------------------------------------------------------------------------


def lock_request(db: Session, request_id: int) -> StockRequest:
    sr = db.execute(
        select(StockRequest).where(StockRequest.id == request_id).with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if sr is None:
        raise NotFoundError("Stock request not found")
    return sr


def get_scoped(db: Session, user: User, request_id: int, *, lock: bool = False) -> StockRequest:
    sr = lock_request(db, request_id) if lock else db.get(StockRequest, request_id)
    if sr is None:
        raise NotFoundError("Stock request not found")
    ensure_reseller_access(user, sr.reseller_id, "Stock request")   # reseller users: own requests only
    return sr


def _event(db: Session, sr: StockRequest, actor: User | None, action: str, summary: str, *,
           from_status: str | None = None, details: dict | None = None, audit: bool = True) -> None:
    db.add(StockRequestEvent(
        stock_request_id=sr.id, action=action, from_status=from_status, to_status=sr.status.value,
        summary=summary, details=details, actor_user_id=actor.id if actor else None, actor_role=_role(actor),
    ))
    if audit:
        record_audit(db, actor_id=actor.id if actor else None, action=f"stock_request.{action.lower()}",
                     entity_type="stock_request", entity_id=sr.id, reseller_id=sr.reseller_id,
                     summary=f"{sr.number}: {summary}",
                     details={"role": _role(actor), "from_status": from_status, "to_status": sr.status.value,
                              **(details or {})})


def notify(db: Session, user_ids: Iterable[int | None], title: str, body: str | None, sr: StockRequest,
           exclude: int | None = None) -> None:
    notify_users(db, user_ids, title, body, link=link(sr), entity_type="stock_request", entity_id=sr.id, exclude=exclude)


def _users_with(db: Session, perm: P) -> list[int]:
    return staff_with(db, perm)


def _requester_audience(db: Session, sr: StockRequest) -> list[int | None]:
    """The requester, the reseller's own users and the reseller's assigned sales representative."""
    reseller = db.get(Reseller, sr.reseller_id)
    return [sr.created_by_user_id, reseller.sales_rep_user_id if reseller else None, *reseller_users(db, sr.reseller_id)]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass
class LineIn:
    product_id: int
    quantity: int
    notes: str | None = None
    find_for_me: bool = False


def _location(db: Session, actor: User, location_id: int) -> Location:
    location = db.get(Location, location_id)
    if location is None or location.type != LocationType.CONSIGNMENT:
        raise BusinessRuleError("Choose a dealer consignment location")
    ensure_reseller_access(actor, location.reseller_id, "Location")
    if not location.is_active:
        raise BusinessRuleError(f"Location {location.code} is inactive")
    _require_active_reseller(db, location.reseller_id)
    return location


def _require_active_reseller(db: Session, reseller_id: int) -> Reseller:
    reseller = db.get(Reseller, reseller_id)
    if reseller is None or reseller.status != ResellerStatus.ACTIVE:
        state = reseller.status.value.replace("_", " ").lower() if reseller else "missing"
        raise BusinessRuleError(f"Dealer account is {state}; stock cannot be requested or approved")
    return reseller


def _validate_lines(db: Session, lines: list[LineIn]) -> None:
    settings = get_settings()
    if not lines:
        raise BusinessRuleError("Add at least one SKU to the request")
    if len(lines) > settings.stock_request_max_lines:
        raise BusinessRuleError(f"A request can have at most {settings.stock_request_max_lines} SKUs")
    seen: set[int] = set()
    for ln in lines:
        product = db.get(Product, ln.product_id)
        if product is None:
            raise BusinessRuleError("Product not found")
        if ln.quantity <= 0:
            raise BusinessRuleError(f"{product.tyre_label}: quantity must be greater than zero")
        if ln.quantity > settings.stock_request_max_line_qty:
            raise BusinessRuleError(
                f"{product.tyre_label}: {ln.quantity} exceeds the limit of {settings.stock_request_max_line_qty} per SKU")
        if not product.is_active:
            raise BusinessRuleError(f"{product.tyre_label} is inactive and cannot be requested")
        if ln.product_id in seen:
            raise BusinessRuleError(f"{product.tyre_label} is listed twice; combine the quantities on one line")
        seen.add(ln.product_id)


def _validate_header(actor: User, priority: Priority, required_date: date | None) -> None:
    if actor.is_reseller_user and priority == Priority.URGENT:
        raise BusinessRuleError("Urgent priority is set by dealership staff; request High priority instead")
    if required_date is not None and required_date < date.today():
        raise BusinessRuleError("Required date cannot be in the past")


def _address(location: Location) -> str | None:
    parts = [location.address_line1, location.address_line2, location.city, location.region, location.postcode,
             location.country]
    text = ", ".join(p for p in parts if p)
    return f"{location.name}, {text}" if text else location.name


def _can_change(actor: User, sr: StockRequest) -> None:
    """The requester, the reseller's own users or the Central Team may change / submit / cancel a request."""
    if actor.id == sr.created_by_user_id or role_has(actor.role, P.STOCK_REQUEST_APPROVE):
        return
    if actor.is_reseller_user and actor.reseller_id == sr.reseller_id:
        return
    raise PermissionDeniedError("Only the requester or the Central Team can change this request")


def _line_summary(db: Session, sr: StockRequest) -> list[dict]:
    skus = {p.id: p.sku for p in db.execute(
        select(Product).where(Product.id.in_([ln.product_id for ln in sr.lines]))).scalars()}
    return [{"sku": skus.get(ln.product_id), "requested": ln.qty_requested, "approved": ln.qty_approved,
             "rejected": ln.qty_rejected, "backordered": ln.qty_backordered} for ln in sr.lines]


# ---------------------------------------------------------------------------
# Draft and submission
# ---------------------------------------------------------------------------


def create(db: Session, actor: User, *, location_id: int, lines: list[LineIn], priority: Priority = Priority.NORMAL,
           required_date: date | None = None, notes: str | None = None, shipping_address: str | None = None,
           submit_now: bool = False) -> StockRequest:
    location = _location(db, actor, location_id)
    _validate_header(actor, priority, required_date)
    _validate_lines(db, lines)
    sr = StockRequest(
        number=next_number(db, "SRQ"), reseller_id=location.reseller_id, location_id=location.id, status=S.DRAFT,
        priority=priority, required_date=required_date, notes=notes,
        shipping_address=shipping_address or _address(location),
        created_by_user_id=actor.id, created_by_role=_role(actor),
    )
    sr.lines = [StockRequestLine(line_no=i + 1, product_id=ln.product_id, qty_requested=ln.quantity, notes=ln.notes,
                                 find_for_me=ln.find_for_me)
                for i, ln in enumerate(lines)]
    db.add(sr)
    db.flush()
    units = sum(ln.quantity for ln in lines)
    behalf = "" if actor.is_reseller_user else f" on behalf of {db.get(Reseller, sr.reseller_id).business_name}"
    _event(db, sr, actor, "CREATED", f"Draft created{behalf}: {len(lines)} SKU(s), {units} unit(s)",
           details={"lines": _line_summary(db, sr)})
    if submit_now:
        submit(db, actor, sr.id)
    return sr


def update_draft(db: Session, actor: User, request_id: int, *, lines: list[LineIn], priority: Priority,
                 required_date: date | None, notes: str | None, shipping_address: str | None) -> StockRequest:
    sr = get_scoped(db, actor, request_id, lock=True)
    if sr.status != S.DRAFT:
        raise ConflictError(f"{sr.number} is {sr.status.value}; only drafts can be edited")
    _can_change(actor, sr)
    _validate_header(actor, priority, required_date)
    _validate_lines(db, lines)
    sr.lines.clear()
    db.flush()
    sr.lines.extend(StockRequestLine(line_no=i + 1, product_id=ln.product_id, qty_requested=ln.quantity,
                                     notes=ln.notes, find_for_me=ln.find_for_me) for i, ln in enumerate(lines))
    sr.priority, sr.required_date, sr.notes = priority, required_date, notes
    sr.shipping_address = shipping_address or sr.shipping_address
    db.flush()
    _event(db, sr, actor, "UPDATED", f"Draft updated: {len(lines)} SKU(s), {sum(ln.quantity for ln in lines)} unit(s)",
           details={"lines": _line_summary(db, sr)})
    return sr


def submit(db: Session, actor: User, request_id: int) -> StockRequest:
    sr = get_scoped(db, actor, request_id, lock=True)
    if sr.status != S.DRAFT:
        raise ConflictError(f"{sr.number} is already {sr.status.value}")
    _can_change(actor, sr)
    _location(db, actor, sr.location_id)
    _validate_lines(db, [LineIn(ln.product_id, ln.qty_requested) for ln in sr.lines])
    if sr.required_date is not None and sr.required_date < date.today():
        raise BusinessRuleError("Required date is in the past; update the draft first")
    sr.status = S.SUBMITTED
    sr.submitted_at = _now()
    units = sum(ln.qty_requested for ln in sr.lines)
    _event(db, sr, actor, "SUBMITTED", f"Submitted for approval: {len(sr.lines)} SKU(s), {units} unit(s)",
           from_status=S.DRAFT.value)
    reseller = db.get(Reseller, sr.reseller_id)
    _hand_to_warehouse(db, actor, sr, reseller)
    to_decide = sum(ln.qty_requested - ln.qty_arranging for ln in sr.lines)
    if to_decide == 0:
        # Everything is being arranged from other dealers: nothing for the Central Team to approve or pick.
        sr.decision = sr.status = S.APPROVED
        sr.closed_at = _now()
        _event(db, sr, None, "STATUS_CHANGED", "Everything on this request is being arranged by the warehouse",
               from_status=S.SUBMITTED.value, audit=False)
        return sr
    notify(db, _users_with(db, P.STOCK_REQUEST_APPROVE), f"{sr.number} is waiting for approval",
           f"{reseller.business_name}: {to_decide} unit(s) across {len(sr.lines)} SKU(s)", sr, exclude=actor.id)
    return sr


# ---------------------------------------------------------------------------
# "Get this tyre for me": what the warehouse cannot supply is found from another dealer
# ---------------------------------------------------------------------------


def _warehouse_available(db: Session, product_ids: Iterable[int]) -> dict[int, int]:
    try:
        warehouse = default_warehouse(db)
    except BusinessRuleError:
        return {}
    rows = db.execute(select(StockBalance).where(StockBalance.location_id == warehouse.id,
                                                 StockBalance.product_id.in_(set(product_ids)))).scalars()
    return {b.product_id: max(0, b.available) for b in rows}


def supply_check(db: Session, lines: list[tuple[int, int]]) -> list[dict]:
    """Yes / no per line: can the warehouse cover the full quantity right now? One query; no stock figures."""
    available = _warehouse_available(db, [pid for pid, _ in lines])
    return [{"product_id": pid, "needs_help": qty > available.get(pid, 0)} for pid, qty in lines]


def _hand_to_warehouse(db: Session, actor: User, sr: StockRequest, reseller: Reseller) -> None:
    """On submission, lines marked "Get this tyre for me" hand their shortfall to the warehouse as a transfer
    request from another dealer. The Central Team then decides only the rest of the line."""
    from app.modules.transfers import service as transfers  # transfers → replenishment → stock requests

    wanted = [ln for ln in sr.lines if ln.find_for_me and ln.qty_arranging == 0]
    if not wanted:
        return
    available = _warehouse_available(db, [ln.product_id for ln in wanted])
    team = staff_in_roles(db, Role.WAREHOUSE_MANAGER, Role.RELATIONSHIP_MANAGER)
    for ln in wanted:
        short = ln.qty_requested - available.get(ln.product_id, 0)
        if short <= 0:
            continue   # the warehouse can supply it after all: the line goes through approval as usual
        product = db.get(Product, ln.product_id)
        t = transfers.request_transfer(
            db, actor, destination_location_id=sr.location_id, product_id=ln.product_id, quantity=short,
            reason=f"{reseller.business_name} asked us to get this tyre for them ({sr.number})", urgency=Priority.HIGH)
        ln.qty_arranging, ln.arranging_transfer_id = short, t.id
        db.flush()
        _event(db, sr, actor, "ARRANGING", f"{short} × {product.tyre_label} handed to the warehouse to find from "
               f"another dealer ({t.number})", details={"sku": product.sku, "quantity": short, "transfer": t.number})
        notify_users(db, team, f"Please find {product.tyre_label} for {reseller.business_name}",
                     f"{short} needed for {sr.number}. The warehouse has none to spare: please arrange it from a "
                     f"dealer who holds it ({t.number}).", link=f"/transfers/{t.id}", entity_type="transfer",
                     entity_id=t.id, exclude=actor.id)


def arranged_transfer_update(db: Session, transfer, what: str, actor_id: int | None) -> None:
    """Called by transfers: tell the dealer when the tyre we arranged is on its way; tell the team if it fell
    through, so the dealer is never left waiting silently."""
    ln = db.execute(select(StockRequestLine).where(StockRequestLine.arranging_transfer_id == transfer.id)
                    ).scalar_one_or_none()
    if ln is None:
        return
    sr = db.get(StockRequest, ln.stock_request_id)
    product = db.get(Product, ln.product_id)
    if what == "COLLECTED":
        notify(db, _requester_audience(db, sr), f"Good news: {product.tyre_label} is on its way",
               f"The tyre we arranged for {sr.number} is on its way to you.", sr, exclude=actor_id)
        _event(db, sr, None, "ARRANGED_ON_ITS_WAY", f"{product.tyre_label} arranged from another dealer is on its way "
               f"({transfer.number})", audit=False)
    elif what in ("REJECTED", "CANCELLED"):
        notify_users(db, staff_in_roles(db, Role.WAREHOUSE_MANAGER, Role.RELATIONSHIP_MANAGER),
                     f"{sr.number}: the dealer is still waiting for {product.tyre_label}",
                     f"{transfer.number} was {what.lower()}. {ln.qty_arranging} still need to be arranged for "
                     f"{db.get(Reseller, sr.reseller_id).business_name}.", link=link(sr),
                     entity_type="stock_request", entity_id=sr.id, exclude=actor_id)
        _event(db, sr, None, "ARRANGING_FELL_THROUGH", f"{transfer.number} was {what.lower()}; the team has been asked "
               "to follow up", audit=False)


def cancel(db: Session, actor: User, request_id: int, reason: str) -> StockRequest:
    sr = get_scoped(db, actor, request_id, lock=True)
    if sr.status not in (S.DRAFT, *PENDING_STATUSES):
        raise ConflictError(f"{sr.number} is {sr.status.value}; only requests not yet decided can be cancelled")
    _can_change(actor, sr)
    prev = sr.status
    sr.status = S.CANCELLED
    sr.closed_at = _now()
    _event(db, sr, actor, "CANCELLED", f"Cancelled: {reason}", from_status=prev.value)
    notify(db, [sr.created_by_user_id], f"{sr.number} was cancelled", reason, sr, exclude=actor.id)
    return sr


# ---------------------------------------------------------------------------
# Central Team review
# ---------------------------------------------------------------------------


def start_review(db: Session, actor: User, request_id: int) -> StockRequest:
    _require(actor, P.STOCK_REQUEST_APPROVE)
    sr = get_scoped(db, actor, request_id, lock=True)
    if sr.status != S.SUBMITTED:
        raise ConflictError(f"{sr.number} is {sr.status.value}; only submitted requests can be taken into review")
    sr.status = S.UNDER_REVIEW
    sr.review_started_at = _now()
    _event(db, sr, actor, "REVIEW_STARTED", f"Under review by {actor.full_name}", from_status=S.SUBMITTED.value)
    notify(db, [sr.created_by_user_id], f"{sr.number} is under review", f"Reviewed by {actor.full_name}", sr,
           exclude=actor.id)
    return sr


def _guard_escalation(db: Session, actor: User, sr: StockRequest) -> None:
    """While a request waits for a Relationship Manager, only that RM or an Administrator may decide it (D10)."""
    if sr.escalated_to_user_id and sr.status in PENDING_STATUSES and actor.id != sr.escalated_to_user_id \
            and actor.role != Role.ADMINISTRATOR:
        rm = db.get(User, sr.escalated_to_user_id)
        raise PermissionDeniedError(f"Waiting for {rm.full_name if rm else 'the Relationship Manager'} to approve")


def escalate(db: Session, actor: User, request_id: int, to_user_id: int, note: str | None) -> StockRequest:
    """Send a request to a Relationship Manager for approval; the warehouse continues once it is approved."""
    _require(actor, P.STOCK_REQUEST_APPROVE)
    sr = get_scoped(db, actor, request_id, lock=True)
    if sr.status not in PENDING_STATUSES:
        raise ConflictError(f"{sr.number} is {sr.status.value}; only requests waiting for a decision can be sent on")
    if sr.escalated_to_user_id:
        raise ConflictError(f"{sr.number} is already waiting for a Relationship Manager")
    rm = db.get(User, to_user_id)
    if rm is None or not rm.is_active or rm.role != Role.RELATIONSHIP_MANAGER:
        raise BusinessRuleError("Choose an active Relationship Manager")
    prev = sr.status
    sr.status = S.UNDER_REVIEW
    sr.review_started_at = sr.review_started_at or _now()
    sr.escalated_to_user_id, sr.escalated_by_user_id, sr.escalated_at = rm.id, actor.id, _now()
    sr.escalation_note = (note or "").strip() or None
    note_tail = f": {sr.escalation_note}" if sr.escalation_note else ""
    _event(db, sr, actor, "ESCALATED", f"Sent to {rm.full_name} for approval{note_tail}",
           from_status=prev.value, details={"to_user_id": rm.id, "note": sr.escalation_note})
    reseller = db.get(Reseller, sr.reseller_id)
    notify(db, [rm.id], f"Your approval is needed: {sr.number}",
           f"{reseller.business_name} · sent by {actor.full_name}{note_tail}", sr)
    return sr


def hand_back(db: Session, actor: User, request_id: int, note: str | None) -> StockRequest:
    """The Relationship Manager (or an Administrator) returns the decision to the warehouse."""
    _require(actor, P.STOCK_REQUEST_APPROVE)
    sr = get_scoped(db, actor, request_id, lock=True)
    if not sr.escalated_to_user_id or sr.status not in PENDING_STATUSES:
        raise ConflictError(f"{sr.number} is not waiting for a Relationship Manager")
    _guard_escalation(db, actor, sr)
    by = sr.escalated_by_user_id
    sr.escalated_to_user_id = sr.escalated_by_user_id = sr.escalated_at = sr.escalation_note = None
    note = (note or "").strip() or None
    _event(db, sr, actor, "HANDED_BACK", "Handed back to the warehouse" + (f": {note}" if note else ""),
           from_status=sr.status.value, details={"note": note})
    notify(db, [by], f"{sr.number} handed back to you", note or f"{actor.full_name} handed the decision back", sr,
           exclude=actor.id)
    return sr


def request_callback(db: Session, actor: User, request_id: int, preferred_time: str, phone: str) -> StockRequest:
    """The dealer (own request) or a sales rep asks the supplier to call about an order (finding 21)."""
    if not actor.is_reseller_user and actor.role != Role.SALES_REP:
        raise PermissionDeniedError("Only the dealer or a sales representative can ask for a call")
    sr = get_scoped(db, actor, request_id)   # a dealer can only reach their own requests (404 otherwise)
    reseller = db.get(Reseller, sr.reseller_id)
    preferred_time, phone = preferred_time.strip(), phone.strip()
    _event(db, sr, actor, "CALLBACK_REQUESTED", f"Call requested: {preferred_time}, {phone}",
           from_status=sr.status.value, details={"preferred_time": preferred_time, "phone": phone})
    notify(db, [*staff_in_roles(db, Role.RELATIONSHIP_MANAGER), reseller.sales_rep_user_id],
           f"{reseller.business_name} would like a call about {sr.number}",
           f"Preferred time {preferred_time} · phone {phone} · asked by {actor.full_name}", sr, exclude=actor.id)
    return sr


@dataclass
class Decision:
    line_id: int
    approve_qty: int
    remainder: RemainderAction = RemainderAction.BACKORDER
    notes: str | None = None


def decide(db: Session, actor: User, request_id: int, decisions: list[Decision],
           notes: str | None = None, approval=None) -> StockRequest:
    """Approve, partially approve or reject line by line. Approved quantities are reserved immediately."""
    _require(actor, P.STOCK_REQUEST_APPROVE)
    sr = get_scoped(db, actor, request_id, lock=True)
    if sr.status not in PENDING_STATUSES:
        raise ConflictError(f"{sr.number} is {sr.status.value}; only submitted requests can be decided")
    _guard_escalation(db, actor, sr)
    _require_active_reseller(db, sr.reseller_id)
    location = db.get(Location, sr.location_id)
    lines = {ln.id: ln for ln in sr.lines}
    given = {d.line_id: d for d in decisions}
    if set(given) != set(lines) or len(given) != len(decisions):
        raise BusinessRuleError("Give exactly one decision for every line of the request")
    warehouse = default_warehouse(db)

    transfers_to_arrange: list = []
    # Validate everything before reserving anything.
    for ln in sr.lines:
        d = given[ln.id]
        product = db.get(Product, ln.product_id)
        to_decide = ln.qty_requested - ln.qty_arranging   # the rest is being arranged by the warehouse
        if d.approve_qty < 0 or d.approve_qty > to_decide:
            raise BusinessRuleError(f"{product.tyre_label}: approved quantity must be 0–{to_decide}")
        remainder = to_decide - d.approve_qty
        if not product.is_active and (d.approve_qty or (remainder and d.remainder == RemainderAction.BACKORDER)):
            raise BusinessRuleError(f"{product.tyre_label} is inactive; it can only be rejected")
        available = get_balance(db, warehouse.id, ln.product_id).available
        if d.approve_qty > available:
            raise BusinessRuleError(
                f"{product.tyre_label}: approving {d.approve_qty} exceeds the {available} available in {warehouse.code}. "
                "Approve what is available and backorder the rest.", code="insufficient_stock")

    if approval is None and any(
            given[ln.id].approve_qty or (given[ln.id].remainder in (RemainderAction.BACKORDER, RemainderAction.TRANSFER)
                                         and ln.qty_requested - ln.qty_arranging - given[ln.id].approve_qty)
            for ln in sr.lines):
        raise BusinessRuleError("Add the approval details: how it was approved, who you spoke to and a comment")

    for ln in sr.lines:
        d = given[ln.id]
        remainder = ln.qty_requested - ln.qty_arranging - d.approve_qty
        ln.qty_approved = d.approve_qty
        ln.qty_backordered = remainder if d.remainder in (RemainderAction.BACKORDER, RemainderAction.TRANSFER) else 0
        ln.qty_rejected = remainder if d.remainder == RemainderAction.REJECT else 0
        ln.decision_notes = d.notes
        demand = ln.qty_approved + ln.qty_backordered
        if demand <= 0:
            continue
        req = replenishment._create(
            db, actor.id, location=location, product_id=ln.product_id, qty=demand,
            reason=ReplenishmentReason.STOCK_REQUEST, origin=Ref("stock_request", sr.id, sr.number),
            priority=sr.priority, expected_date=sr.required_date, notes=ln.notes or f"Stock request {sr.number}",
            auto_allocate=False,
        )
        ln.replenishment_request_id = req.id
        db.flush()
        if ln.qty_approved:
            alloc = replenishment.try_allocate(db, actor.id, req, ln.qty_approved, warehouse)
            if alloc is None or alloc.quantity != ln.qty_approved:
                raise ConflictError("Warehouse stock changed while approving; reload and try again",
                                    code="insufficient_stock")
        if d.remainder == RemainderAction.TRANSFER and ln.qty_backordered:
            transfers_to_arrange.append((ln, req))

    # "Arrange the rest from another dealer": a transfer request covering each such backorder, for the warehouse
    # to choose the dealer who holds it, approve and arrange the pick-up.
    arranged_now = []
    if transfers_to_arrange:
        from app.modules.transfers import service as transfers  # transfers → replenishment → stock requests

        reseller = db.get(Reseller, sr.reseller_id)
        for ln, req in transfers_to_arrange:
            t = transfers.request_transfer(
                db, actor, destination_location_id=sr.location_id, product_id=ln.product_id,
                quantity=ln.qty_backordered, destination_request_id=req.id, urgency=sr.priority,
                reason=f"Rest of {sr.number} for {reseller.business_name}: arranged from another dealer")
            arranged_now.append(t)
            product = db.get(Product, ln.product_id)
            _event(db, sr, actor, "ARRANGING", f"{ln.qty_backordered} × {product.tyre_label} to be arranged from "
                   f"another dealer ({t.number})", details={"sku": product.sku, "quantity": ln.qty_backordered,
                                                           "transfer": t.number})
    approved = sum(ln.qty_approved for ln in sr.lines)
    backordered = sum(ln.qty_backordered for ln in sr.lines)
    rejected = sum(ln.qty_rejected for ln in sr.lines)
    arranging = sum(ln.qty_arranging for ln in sr.lines)
    if approved == 0 and backordered == 0 and arranging == 0:
        outcome = S.REJECTED
    elif all(ln.qty_approved + ln.qty_arranging == ln.qty_requested for ln in sr.lines):
        outcome = S.APPROVED
    else:
        outcome = S.PARTIALLY_APPROVED
    prev = sr.status
    sr.decision = sr.status = outcome
    sr.reviewed_by_user_id, sr.reviewed_by_role, sr.reviewed_at = actor.id, _role(actor), _now()
    sr.review_notes = notes
    if approval is not None:
        sr.approval_method, sr.approval_contact, sr.approval_comments = \
            approval.method.value, approval.contact, approval.comments
    if outcome == S.REJECTED:
        sr.closed_at = sr.reviewed_at
    label = outcome.value.replace("_", " ").capitalize()
    summary = f"{label}: {approved} approved and reserved, {backordered} backordered, {rejected} rejected"
    if arranging:
        summary += f", {arranging} being arranged by the warehouse"
    _event(db, sr, actor, outcome.value, summary + (f" — {notes}" if notes else ""), from_status=prev.value,
           details={"lines": _line_summary(db, sr), "approved": approved, "backordered": backordered,
                    "rejected": rejected,
                    **({"approval": {"method": approval.method.value, "contact": approval.contact,
                                     "comments": approval.comments}} if approval is not None else {})})
    if rejected:
        # Any quantity not supplied: the dealer's users and the requester get the kind standard message (D5),
        # never the internal reason. Other staff (the dealer's sales rep) get the normal summary.
        kind_audience = {sr.created_by_user_id, *reseller_users(db, sr.reseller_id)}
        body = KIND_REJECTION + (f" {approved} tyre(s) of your order are being prepared." if approved else "")
        notify(db, kind_audience, f"Update on your order {sr.number}", body, sr, exclude=actor.id)
        notify(db, [u for u in _requester_audience(db, sr) if u not in kind_audience],
               f"{sr.number} {label.lower()}", summary, sr, exclude=actor.id)
    else:
        notify(db, _requester_audience(db, sr), f"{sr.number} {label.lower()}", summary, sr, exclude=actor.id)
    if approved:
        # Explicit roles: the RM also holds STOCK_REQUEST_FULFIL (P-028) but this is warehouse work.
        notify(db, staff_in_roles(db, Role.WAREHOUSE_MANAGER, Role.ADMINISTRATOR), f"{sr.number} approved — ready to pick",
               f"{approved} unit(s) reserved for {db.get(Reseller, sr.reseller_id).business_name}", sr,
               exclude=actor.id)
    return sr


def reject(db: Session, actor: User, request_id: int, reason: str) -> StockRequest:
    _require(actor, P.STOCK_REQUEST_APPROVE)
    sr = get_scoped(db, actor, request_id, lock=True)
    if sr.status not in PENDING_STATUSES:
        raise ConflictError(f"{sr.number} is {sr.status.value}; only submitted requests can be rejected")
    _guard_escalation(db, actor, sr)
    return decide(db, actor, request_id,
                  [Decision(ln.id, 0, RemainderAction.REJECT, None) for ln in sr.lines], reason)


# ---------------------------------------------------------------------------
# Reservations after approval
# ---------------------------------------------------------------------------


def _line(sr: StockRequest, line_id: int) -> StockRequestLine:
    ln = next((x for x in sr.lines if x.id == line_id), None)
    if ln is None:
        raise NotFoundError("Request line not found")
    return ln


def reserve_backorder(db: Session, actor: User, request_id: int, line_id: int, qty: int | None) -> StockRequest:
    """Reserve newly available warehouse stock for a backordered line (backordered → approved)."""
    _require(actor, P.STOCK_REQUEST_APPROVE)
    sr = get_scoped(db, actor, request_id, lock=True)
    if sr.status not in FULFILMENT_STATUSES:
        raise ConflictError("Stock can only be reserved for approved requests")
    ln = _line(sr, line_id)
    if not ln.replenishment_request_id or ln.qty_backordered <= 0:
        raise ConflictError("This line has no backordered quantity")
    req = replenishment.lock_request(db, ln.replenishment_request_id)
    open_backorder = min(ln.qty_backordered, req.qty_awaiting_supply)
    want = open_backorder if qty is None else qty
    if want <= 0 or want > open_backorder:
        raise BusinessRuleError(f"Between 1 and {open_backorder} can be reserved on this line")
    _require_active_reseller(db, sr.reseller_id)
    replenishment.allocate(db, actor, req.id, want)   # sync moves the quantity from backordered to approved
    product = db.get(Product, ln.product_id)
    _event(db, sr, actor, "RESERVED", f"{product.tyre_label}: reserved {want} backordered unit(s)",
           details={"sku": product.sku, "quantity": want})
    return sr


def release(db: Session, actor: User, request_id: int, line_id: int, reason: str,
            to_backorder: bool = False) -> StockRequest:
    """Release a line's reserved (not yet shipped) stock back to warehouse availability."""
    _require(actor, P.STOCK_REQUEST_APPROVE)
    sr = get_scoped(db, actor, request_id, lock=True)
    if sr.status not in FULFILMENT_STATUSES:
        raise ConflictError("Only approved requests hold reserved stock")
    ln = _line(sr, line_id)
    if not ln.replenishment_request_id:
        raise ConflictError("Nothing is reserved on this line")
    req = replenishment.lock_request(db, ln.replenishment_request_id)
    reserved = req.qty_allocated
    if reserved <= 0:
        raise ConflictError("Nothing is reserved on this line (it may already have shipped)")
    allocs = db.execute(select(ReplenishmentAllocation.id).where(
        ReplenishmentAllocation.request_id == req.id, ReplenishmentAllocation.status == AllocationStatus.ACTIVE,
    ).order_by(ReplenishmentAllocation.id)).scalars().all()
    for alloc_id in allocs:
        replenishment.release_allocation(db, actor.id, alloc_id, reason)
    if to_backorder:
        ln.qty_approved -= reserved
        ln.qty_backordered += reserved
    else:
        ln.qty_released += reserved
        replenishment.cancel_open_quantity(db, actor.id, req, reserved, reason, Ref("stock_request", sr.id, sr.number))
    db.flush()
    sync(db, sr)
    product = db.get(Product, ln.product_id)
    where = "returned to backorder" if to_backorder else "cancelled"
    _event(db, sr, actor, "RELEASED", f"{product.tyre_label}: released {reserved} reserved unit(s), {where} — {reason}",
           details={"sku": product.sku, "quantity": reserved, "to_backorder": to_backorder, "reason": reason})
    notify(db, _requester_audience(db, sr), f"{sr.number}: reserved stock released",
           f"{product.tyre_label}: {reserved} unit(s) {where}", sr, exclude=actor.id)
    return sr


# ---------------------------------------------------------------------------
# Fulfilment
# ---------------------------------------------------------------------------


@dataclass
class LineFulfilment:
    reserved: int = 0
    in_transit: int = 0
    delivered: int = 0
    backorder_open: int = 0
    cancelled: int = 0

    @property
    def shipped(self) -> int:
        return self.in_transit + self.delivered


def fulfilment(db: Session, sr: StockRequest) -> dict[int, LineFulfilment]:
    ids = [ln.replenishment_request_id for ln in sr.lines if ln.replenishment_request_id]
    reqs = {r.id: r for r in db.execute(select(ReplenishmentRequest).where(ReplenishmentRequest.id.in_(ids))).scalars()} \
        if ids else {}
    out = {}
    for ln in sr.lines:
        r = reqs.get(ln.replenishment_request_id)
        out[ln.id] = LineFulfilment(r.qty_allocated, r.qty_in_transit, r.qty_delivered, max(0, r.qty_awaiting_supply),
                                    r.qty_cancelled) if r else LineFulfilment()
    return out


def mark_ready(db: Session, actor: User, request_id: int) -> StockRequest:
    _require(actor, P.STOCK_REQUEST_FULFIL)
    sr = get_scoped(db, actor, request_id, lock=True)
    if sr.status not in FULFILMENT_STATUSES:
        raise ConflictError(f"{sr.number} is {sr.status.value}; it must be approved first")
    reserved = sum(f.reserved for f in fulfilment(db, sr).values())
    if reserved <= 0:
        raise ConflictError("Nothing is reserved to prepare for shipment")
    prev = sr.status
    sr.ready_at = _now()
    _quiet(db, sr, lambda: sync(db, sr))
    _event(db, sr, actor, "READY_FOR_SHIPMENT", f"Picked and packed: {reserved} unit(s) ready for shipment",
           from_status=prev.value, details={"quantity": reserved})
    notify(db, _requester_audience(db, sr), f"{sr.number} is ready for shipment",
           f"{reserved} unit(s) packed at the warehouse", sr, exclude=actor.id)
    return sr


def ship(db: Session, actor: User, request_id: int, *, carrier: str | None, tracking_number: str | None = None,
         shipping_address: str | None = None, notes: str | None = None,
         quantities: dict[int, int] | None = None, shipping_method: str = "COURIER",
         carried_by_user_id: int | None = None) -> Delivery:
    """Create the shipment for reserved stock. quantities: {line_id: qty}; omitted = all reserved on every line."""
    _require(actor, P.STOCK_REQUEST_FULFIL)
    sr = get_scoped(db, actor, request_id, lock=True)
    if sr.status not in FULFILMENT_STATUSES:
        raise ConflictError(f"{sr.number} is {sr.status.value}; stock cannot be shipped before approval")
    if shipping_method == "COURIER" and (not carrier or not carrier.strip()):
        raise BusinessRuleError("Enter the carrier")
    if quantities is not None:
        unknown = set(quantities) - {ln.id for ln in sr.lines}
        if unknown:
            raise BusinessRuleError(f"Lines {sorted(unknown)} are not on {sr.number}")
    fil = fulfilment(db, sr)
    plan: list[tuple[int, int]] = []
    shipped_units = 0
    for ln in sr.lines:
        reserved = fil[ln.id].reserved
        qty = reserved if quantities is None else quantities.get(ln.id, 0)
        if qty < 0 or qty > reserved:
            sku = db.get(Product, ln.product_id).sku
            raise BusinessRuleError(f"{sku}: cannot ship {qty}; {reserved} approved unit(s) are reserved and unshipped")
        if qty > 0:
            plan.append((ln.replenishment_request_id, qty))
            shipped_units += qty
    if not plan:
        raise BusinessRuleError("Nothing reserved to ship")
    prev = sr.status
    address = (shipping_address or "").strip() or sr.shipping_address

    def go() -> Delivery:
        d = replenishment.dispatch(db, actor, to_location_id=sr.location_id, lines=plan,
                                   carrier_reference=(carrier or "").strip() or None, notes=notes,
                                   tracking_number=tracking_number, shipping_address=address, stock_request_id=sr.id,
                                   shipping_method=shipping_method, carried_by_user_id=carried_by_user_id)
        sr.ready_at = None
        sync(db, sr)
        return d

    delivery = _quiet(db, sr, go)
    via = delivery.carrier_reference or carrier
    track = f", tracking {tracking_number}" if tracking_number else ""
    _event(db, sr, actor, "SHIPPED", f"Shipped {shipped_units} unit(s) on {delivery.number} via {via}{track}",
           from_status=prev.value, details={"delivery": delivery.number, "carrier": via, "method": shipping_method,
                                            "tracking_number": tracking_number, "quantity": shipped_units})
    notify(db, _requester_audience(db, sr), f"{sr.number} has shipped",
           f"{shipped_units} unit(s) on {delivery.number} via {via}{track}", sr, exclude=actor.id)
    if delivery.carried_by_user_id:
        notify(db, [delivery.carried_by_user_id], f"Please deliver {delivery.number}",
               f"{shipped_units} unit(s) for {db.get(Reseller, sr.reseller_id).business_name}. Confirm delivery on "
               "arrival.", sr, exclude=actor.id)
    return delivery


def confirm_delivery(db: Session, actor: User, request_id: int, delivery_id: int, *, received: dict[int, int] | None,
                     delivered_on: date | None = None, reference: str | None = None,
                     notes: str | None = None, received_by_name: str | None = None,
                     photos: list[str] | None = None) -> Delivery:
    """Confirm receipt of one shipment. received: {delivery_line_id: qty}; omitted lines = fully received."""
    _require(actor, P.DELIVERY_CONFIRM)
    sr = get_scoped(db, actor, request_id, lock=True)
    delivery = db.get(Delivery, delivery_id)
    if delivery is None or delivery.stock_request_id != sr.id:
        raise NotFoundError("Shipment not found on this request")
    prev = sr.status

    def go() -> Delivery:
        d = replenishment.receive_delivery(db, actor, delivery_id, received, notes, delivered_on, reference,
                                           received_by_name, photos)
        sync(db, sr)
        return d

    delivery = _quiet(db, sr, go)
    got = sum(ln.qty_received for ln in delivery.lines)
    sent = sum(ln.qty_dispatched for ln in delivery.lines)
    short = f"; {sent - got} short (stays in transit until resolved)" if got < sent else ""
    _event(db, sr, actor, "DELIVERED", f"Delivery {delivery.number} confirmed: {got} of {sent} unit(s) received{short}",
           from_status=prev.value, details={"delivery": delivery.number, "received": got, "shipped": sent,
                                            "delivered_on": delivery.delivered_on.isoformat(), "reference": reference})
    notify(db, [sr.created_by_user_id, sr.reviewed_by_user_id, delivery.dispatched_by_user_id],
           f"{sr.number}: delivery confirmed", f"{got} of {sent} unit(s) received at the dealer{short}", sr,
           exclude=actor.id)
    return delivery


# ---------------------------------------------------------------------------
# Status synchronisation with the replenishment workflow
# ---------------------------------------------------------------------------


def _quiet(db: Session, sr: StockRequest, fn):
    """Run fn while status changes of sr are recorded by the caller (no duplicate history entries)."""
    quiet: set[int] = db.info.setdefault(_QUIET, set())
    quiet.add(sr.id)
    try:
        return fn()
    finally:
        quiet.discard(sr.id)


def sync(db: Session, sr: StockRequest) -> None:
    """Derive the fulfilment status from the linked replenishment requests.

    Also converts backordered quantity to approved when warehouse stock gets reserved for it elsewhere (for example
    from the Backorders allocation proposal), so "shipped ≤ approved" always holds.
    """
    if sr.decision is None or sr.status not in FULFILMENT_STATUSES:
        return
    ids = [ln.replenishment_request_id for ln in sr.lines if ln.replenishment_request_id]
    reqs = {r.id: r for r in db.execute(select(ReplenishmentRequest).where(ReplenishmentRequest.id.in_(ids))).scalars()} \
        if ids else {}
    reserved = in_transit = delivered = awaiting = 0
    for ln in sr.lines:
        r = reqs.get(ln.replenishment_request_id)
        if r is None:
            continue
        committed = r.qty_allocated + r.qty_in_transit + r.qty_delivered
        gain = committed - (ln.qty_approved - ln.qty_released)
        if gain > 0 and ln.qty_backordered > 0:
            take = min(gain, ln.qty_backordered)
            ln.qty_backordered -= take
            ln.qty_approved += take
        reserved += r.qty_allocated
        in_transit += r.qty_in_transit
        delivered += r.qty_delivered
        awaiting += max(0, r.qty_awaiting_supply)
    if in_transit > 0:
        new = S.SHIPPED
    elif reserved > 0:
        new = S.READY_FOR_SHIPMENT if sr.ready_at else sr.decision
    elif delivered > 0:
        new = S.DELIVERED
    else:
        new = sr.decision
    sr.closed_at = _now() if new == S.DELIVERED and awaiting == 0 else None
    if new == sr.status:
        return
    prev = sr.status
    sr.status = new
    db.flush()
    if sr.id in db.info.get(_QUIET, set()):
        return
    pretty = new.value.replace("_", " ").lower()
    _event(db, sr, None, "STATUS_CHANGED", f"Status {prev.value.replace('_', ' ').lower()} → {pretty}",
           from_status=prev.value, audit=False)
    if new in (S.SHIPPED, S.DELIVERED):
        notify(db, _requester_audience(db, sr), f"{sr.number} {pretty}", None, sr)


def sync_for_replenishment(db: Session, request_ids: Iterable[int]) -> None:
    ids = {i for i in request_ids if i is not None}
    if not ids:
        return
    sr_ids = db.execute(select(StockRequestLine.stock_request_id).distinct()
                        .where(StockRequestLine.replenishment_request_id.in_(ids))).scalars().all()
    for sr_id in sorted(sr_ids):
        sr = db.get(StockRequest, sr_id)
        if sr is not None:
            sync(db, sr)
