"""Inter-reseller transfers of unsold consignment stock (Scenario 3).

A transfer is NOT a sale: it never creates sale lines or invoices. The source reseller receives a linked
replenishment obligation when stock is collected. See docs/INVENTORY_RULES.md §6.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.numbering import next_number
from app.core.permissions import P, Role, role_has
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product
from app.modules.customers.models import (
    ConsignmentAgreement,
    Location,
    LocationType,
    Reseller,
    ResellerStatus,
    TransferConsent,
)
from app.modules.identity.models import User
from app.modules.identity.scoping import scoped_reseller_id
from app.modules.inventory.models import ReservationPurpose, StockBalance, StockReservation, TxnType
from app.modules.inventory.service import Ledger, Ref, default_warehouse, get_balance, system_location
from app.modules.notifications.service import notify_users, reseller_users
from app.modules.proofs import service as proofs
from app.modules.replenishment import service as replenishment
from app.modules.replenishment.models import OPEN_STATUSES, Priority, ReplenishmentRequest
from app.modules.transfers.models import Transfer, TransferStatus


def _now() -> datetime:
    return datetime.now(UTC)


def _arranged(db: Session, t: Transfer, what: str, actor_id: int) -> None:
    """Keep a dealer's "Get this tyre for me" stock request informed (no-op for other transfers)."""
    from app.modules.stock_requests import service as stock_requests  # stock requests import this module

    stock_requests.arranged_transfer_update(db, t, what, actor_id)


def lock_transfer(db: Session, transfer_id: int) -> Transfer:
    t = db.execute(select(Transfer).where(Transfer.id == transfer_id).with_for_update()
                   .execution_options(populate_existing=True)).scalar_one_or_none()
    if t is None:
        raise NotFoundError("Transfer not found")
    return t


def get_transfer(db: Session, user: User, transfer_id: int) -> Transfer:
    t = db.get(Transfer, transfer_id)
    restricted = scoped_reseller_id(user)
    if t is None or (restricted is not None and restricted not in (t.source_reseller_id, t.destination_reseller_id)):
        raise NotFoundError("Transfer not found")
    return t


def _consignment_location(db: Session, location_id: int, role: str) -> tuple[Location, Reseller]:
    loc = db.get(Location, location_id)
    if loc is None or loc.type != LocationType.CONSIGNMENT:
        raise BusinessRuleError(f"The {role} must be a dealer consignment location")
    if not loc.is_active:
        raise BusinessRuleError(f"{loc.code} is inactive")
    reseller = db.get(Reseller, loc.reseller_id)
    if reseller.status != ResellerStatus.ACTIVE:
        raise BusinessRuleError(f"The {role} dealer {reseller.account_ref} is {reseller.status}")
    return loc, reseller


def _consent(db: Session, reseller_id: int) -> TransferConsent:
    agreement = db.execute(
        select(ConsignmentAgreement).where(ConsignmentAgreement.reseller_id == reseller_id)
    ).scalar_one_or_none()
    return agreement.transfer_consent if agreement else TransferConsent.PER_TRANSFER


def _cover_destination(db: Session, t: Transfer, delta: int, *, delivered: int = 0, actor_id: int | None,
                       event: str | None = None, reason: str | None = None) -> None:
    """Adjust the linked destination request: delta to transfer-covered qty, plus delivered qty."""
    if t.destination_request_id is None or (delta == 0 and delivered == 0):
        return
    req = replenishment.lock_request(db, t.destination_request_id)
    req.qty_transfer_covered += delta
    req.qty_delivered += delivered
    replenishment._refresh(req)
    if event:
        replenishment._event(db, req, event, abs(delta) or delivered, actor_id, Ref("transfer", t.id, t.number), reason)
    db.flush()
    replenishment._sync_stock_requests(db, [req.id])   # a stock request's backorder covered by this transfer


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@dataclass
class SourceOption:
    location_id: int
    location_code: str
    location_name: str
    reseller_id: int
    reseller_name: str
    account_ref: str
    on_hand: int
    reserved: int
    blocked: int
    available: int
    transfer_consent: TransferConsent
    eligible: bool
    ineligible_reason: str | None


def find_sources(db: Session, product_id: int, *, exclude_location_id: int | None = None,
                 quantity: int = 1) -> tuple[int, list[SourceOption]]:
    """Exact-SKU search across consignment locations. Returns (warehouse available, options)."""
    if db.get(Product, product_id) is None:
        raise NotFoundError("Product not found")
    try:
        wh_available = get_balance(db, default_warehouse(db).id, product_id).available
    except BusinessRuleError:
        wh_available = 0
    rows = db.execute(
        select(StockBalance, Location, Reseller)
        .join(Location, Location.id == StockBalance.location_id)
        .join(Reseller, Reseller.id == Location.reseller_id)
        .where(StockBalance.product_id == product_id, Location.type == LocationType.CONSIGNMENT,
               StockBalance.on_hand > 0)
        .order_by(Location.code)
    ).tuples()
    options = []
    for bal, loc, reseller in rows:
        if loc.id == exclude_location_id:
            continue
        consent = _consent(db, reseller.id)
        reason = None
        if reseller.status != ResellerStatus.ACTIVE:
            reason = f"Dealer is {reseller.status}"
        elif not loc.is_active:
            reason = "Location inactive"
        elif consent == TransferConsent.NOT_ALLOWED:
            reason = "Agreement does not allow transfers out"
        elif bal.available < quantity:
            reason = f"Only {bal.available} available (excludes reserved/blocked)"
        options.append(SourceOption(
            location_id=loc.id, location_code=loc.code, location_name=loc.name, reseller_id=reseller.id,
            reseller_name=reseller.business_name, account_ref=reseller.account_ref, on_hand=bal.on_hand,
            reserved=bal.reserved, blocked=bal.blocked, available=bal.available, transfer_consent=consent,
            eligible=reason is None, ineligible_reason=reason,
        ))
    options.sort(key=lambda o: (not o.eligible, -o.available, o.location_code))
    return wh_available, options


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def request_transfer(db: Session, actor: User, *, destination_location_id: int, product_id: int, quantity: int,
                     reason: str, urgency: Priority = Priority.HIGH,
                     destination_request_id: int | None = None, notes: str | None = None) -> Transfer:
    dest, dest_reseller = _consignment_location(db, destination_location_id, "destination")
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise BusinessRuleError("Product not found or inactive")
    if quantity <= 0:
        raise BusinessRuleError("Quantity must be positive")
    t = Transfer(number=next_number(db, "TRF"), product_id=product.id, quantity=quantity,
                 destination_location_id=dest.id, destination_reseller_id=dest_reseller.id, reason=reason,
                 urgency=urgency, status=TransferStatus.REQUESTED, requested_by_user_id=actor.id, notes=notes)
    if destination_request_id is not None:
        req = replenishment.lock_request(db, destination_request_id)
        if req.location_id != dest.id or req.product_id != product.id or req.status not in OPEN_STATUSES:
            raise BusinessRuleError("The linked request must be an open request for the same location and SKU")
        if quantity > req.qty_awaiting_supply:
            raise BusinessRuleError(f"{req.number} has only {req.qty_awaiting_supply} awaiting supply")
        t.destination_request_id = req.id
    db.add(t)
    db.flush()
    record_audit(db, actor_id=actor.id, action="transfer.request", entity_type="transfer", entity_id=t.id,
                 reseller_id=dest_reseller.id,
                 summary=f"{t.number}: {quantity} × {product.sku} requested for {dest.code} ({reason})")
    return t


def approve(db: Session, actor: User, transfer_id: int, *, source_location_id: int,
            approval_notes: str | None = None, source_consent_reference: str | None = None) -> Transfer:
    t = lock_transfer(db, transfer_id)
    if t.status != TransferStatus.REQUESTED:
        raise ConflictError(f"{t.number} is {t.status}")
    if source_location_id == t.destination_location_id:
        raise BusinessRuleError("Source and destination must be different locations")
    source, source_reseller = _consignment_location(db, source_location_id, "source")
    consent = _consent(db, source_reseller.id)
    if consent == TransferConsent.NOT_ALLOWED:
        raise BusinessRuleError(f"{source_reseller.account_ref}'s agreement does not allow transfers out")
    if consent == TransferConsent.PER_TRANSFER and not (source_consent_reference or "").strip():
        raise BusinessRuleError(
            f"{source_reseller.account_ref}'s agreement requires recorded consent for each transfer"
        )
    if t.destination_request_id is not None:
        req = replenishment.lock_request(db, t.destination_request_id)
        if t.quantity > req.qty_awaiting_supply:
            raise ConflictError(f"{req.number} now has only {req.qty_awaiting_supply} awaiting supply")
    ref = Ref("transfer", t.id, t.number)
    ledger = Ledger(db, TxnType.RESERVATION, actor_id=actor.id, approved_by_id=actor.id, ref=ref,
                    reason="Transfer approved")
    reservation = ledger.reserve(source, t.product_id, t.quantity, ReservationPurpose.TRANSFER, ref)
    t.source_location_id = source.id
    t.source_reseller_id = source_reseller.id
    t.reservation_id = reservation.id
    t.status = TransferStatus.APPROVED
    t.approved_by_user_id = actor.id
    t.approved_at = _now()
    t.approval_notes = approval_notes
    t.source_consent_reference = source_consent_reference
    db.flush()
    _cover_destination(db, t, t.quantity, actor_id=actor.id, event="TRANSFER_COVERED", reason="Transfer approved")
    record_audit(db, actor_id=actor.id, action="transfer.approve", entity_type="transfer", entity_id=t.id,
                 reseller_id=t.destination_reseller_id,
                 summary=f"Approved {t.number}: {t.quantity} from {source.code} to destination; consent "
                         f"{source_consent_reference or consent.value}",
                 details={"source_reseller_id": source_reseller.id, "approval_notes": approval_notes})
    record_audit(db, actor_id=actor.id, action="transfer.approve", entity_type="transfer", entity_id=t.id,
                 reseller_id=source_reseller.id, summary=f"{t.number}: {t.quantity} reserved at {source.code} for transfer")
    return t


# ---------------------------------------------------------------------------
# How the tyres travel (release 1.11, finding 23)
# ---------------------------------------------------------------------------


def link(t: Transfer) -> str:
    return f"/transfers/{t.id}"


def _where(db: Session, location_id: int) -> str:
    loc = db.get(Location, location_id)
    return f"{db.get(Reseller, loc.reseller_id).business_name}, {replenishment._address(loc)}"


def via_warehouse(t: Transfer) -> bool:
    return t.route == "VIA_WAREHOUSE"


def warehouse_receive(db: Session, actor: User, transfer_id: int, *, notes: str | None = None,
                      photos: list[str] | None = None) -> Transfer:
    """Via-warehouse transfers: the warehouse records that it received and checked the tyres on their way to the
    destination dealer. No stock moves (they stay in transit); the carrying Sales Rep is told to deliver."""
    t = lock_transfer(db, transfer_id)
    if not via_warehouse(t):
        raise BusinessRuleError(f"{t.number} goes direct to the dealer, not via the warehouse")
    if t.status != TransferStatus.IN_TRANSIT:
        raise ConflictError(f"{t.number} is {t.status}; the warehouse checks it after collection")
    if t.warehouse_received_at is not None:
        raise ConflictError(f"{t.number} was already received at the warehouse")
    notes = (notes or "").strip()
    if len(notes) < 3:
        raise BusinessRuleError("Add a short note: how many arrived and their condition")
    t.warehouse_received_at, t.warehouse_received_by_user_id, t.warehouse_check_notes = _now(), actor.id, notes
    for data_url in photos or []:
        proofs.add_photo(db, actor, "transfer", t.id, data_url)
    db.flush()
    product = db.get(Product, t.product_id)
    record_audit(db, actor_id=actor.id, action="transfer.warehouse_receive", entity_type="transfer", entity_id=t.id,
                 reseller_id=t.destination_reseller_id,
                 summary=f"{t.number}: {t.qty_in_transit} × {product.sku} received and checked at the warehouse ({notes})")
    if t.carried_by_user_id:
        notify_users(db, [t.carried_by_user_id], f"{t.number} is checked: please deliver it",
                     f"{t.qty_in_transit} × {product.tyre_label} checked at the warehouse. Deliver to "
                     f"{_where(db, t.destination_location_id)}.", link=link(t), entity_type="transfer",
                     entity_id=t.id, exclude=actor.id)
    return t


def arrange_shipping(db: Session, actor: User, transfer_id: int, *, shipping_method: str,
                     carrier_reference: str | None = None, tracking_number: str | None = None,
                     carried_by_user_id: int | None = None, route: str = "DIRECT") -> Transfer:
    """Say who carries the tyres from the source dealer to the destination; allowed until collection."""
    t = lock_transfer(db, transfer_id)
    if t.status != TransferStatus.APPROVED:
        raise ConflictError(f"{t.number} is {t.status}; pick-up is arranged after approval and before collection")
    carrier_reference = (carrier_reference or "").strip() or None
    if shipping_method == "COURIER" and not carrier_reference:
        raise BusinessRuleError("Enter the courier")
    carrier = replenishment._shipping(db, shipping_method, carried_by_user_id, carrier_reference)
    t.shipping_method = shipping_method
    t.carrier_reference = carrier
    t.tracking_number = ((tracking_number or "").strip() or None) if shipping_method == "COURIER" else None
    t.carried_by_user_id = carried_by_user_id if shipping_method == "SALES_REP" else None
    t.route = route
    t.shipping_arranged_at, t.shipping_arranged_by_user_id = _now(), actor.id
    db.flush()
    record_audit(db, actor_id=actor.id, action="transfer.shipping", entity_type="transfer", entity_id=t.id,
                 reseller_id=t.destination_reseller_id,
                 summary=f"{t.number}: pick-up arranged ({carrier}, {'via the warehouse' if via_warehouse(t) else 'direct'})")
    if t.carried_by_user_id:
        product = db.get(Product, t.product_id)
        notify_users(db, [t.carried_by_user_id], f"Please collect {t.number} ({t.quantity} × {product.tyre_label})",
                     f"Collect from {_where(db, t.source_location_id)}, "
                     + ("bring the tyres to the warehouse to be checked, then deliver to " if via_warehouse(t)
                        else "and deliver to ")
                     + f"{_where(db, t.destination_location_id)}.", link=link(t), entity_type="transfer",
                     entity_id=t.id, exclude=actor.id)
    return t


def reject(db: Session, actor: User, transfer_id: int, reason: str) -> Transfer:
    t = lock_transfer(db, transfer_id)
    if t.status != TransferStatus.REQUESTED:
        raise ConflictError(f"{t.number} is {t.status}")
    t.status = TransferStatus.REJECTED
    t.cancel_reason = reason
    t.cancelled_by_user_id = actor.id
    t.cancelled_at = _now()
    record_audit(db, actor_id=actor.id, action="transfer.reject", entity_type="transfer", entity_id=t.id,
                 reseller_id=t.destination_reseller_id, summary=f"Rejected {t.number}: {reason}")
    _arranged(db, t, "REJECTED", actor.id)
    return t


def cancel(db: Session, actor: User, transfer_id: int, reason: str) -> Transfer:
    """Cancel before collection. Releases the source reservation; no obligation exists yet (A-003)."""
    t = lock_transfer(db, transfer_id)
    if t.status not in (TransferStatus.REQUESTED, TransferStatus.APPROVED):
        raise ConflictError(
            f"{t.number} is {t.status}; after collection use 'return to source' to reverse the movement"
        )
    if t.status == TransferStatus.APPROVED:
        reservation = db.get(StockReservation, t.reservation_id)
        Ledger(db, TxnType.RESERVATION_RELEASE, actor_id=actor.id, ref=Ref("transfer", t.id, t.number),
               reason=f"Transfer cancelled: {reason}").release(reservation)
        _cover_destination(db, t, -t.quantity, actor_id=actor.id, event="TRANSFER_COVER_RELEASED", reason=reason)
    t.status = TransferStatus.CANCELLED
    t.cancel_reason = reason
    t.cancelled_by_user_id = actor.id
    t.cancelled_at = _now()
    db.flush()
    record_audit(db, actor_id=actor.id, action="transfer.cancel", entity_type="transfer", entity_id=t.id,
                 reseller_id=t.destination_reseller_id, summary=f"Cancelled {t.number} before collection: {reason}")
    _arranged(db, t, "CANCELLED", actor.id)
    return t


def collect(db: Session, actor: User, transfer_id: int, *, quantity: int | None = None,
            notes: str | None = None, collected_from_name: str | None = None,
            photos: list[str] | None = None) -> Transfer:
    """Collect from the source: stock moves into transit and the source is owed replacement."""
    t = lock_transfer(db, transfer_id)
    if t.status != TransferStatus.APPROVED:
        raise ConflictError(f"{t.number} is {t.status}")
    collected_from_name = (collected_from_name or "").strip() or None
    if t.carried_by_user_id:
        # A sales rep was asked to carry it: only that rep (or an Administrator) records the collection.
        if actor.id != t.carried_by_user_id and actor.role != Role.ADMINISTRATOR:
            rep = db.get(User, t.carried_by_user_id)
            raise PermissionDeniedError(f"{rep.full_name if rep else 'The sales representative'} is collecting "
                                        f"{t.number}: only they can record the collection")
        if not collected_from_name or len(collected_from_name) < 2:
            raise BusinessRuleError("Enter the name of the person at the dealer who handed the tyres over")
    qty = t.quantity if quantity is None else quantity
    if qty <= 0 or qty > t.quantity:
        raise BusinessRuleError(f"Collected quantity must be 1–{t.quantity}")
    source = db.get(Location, t.source_location_id)
    reservation = db.get(StockReservation, t.reservation_id)
    ref = Ref("transfer", t.id, t.number)
    ledger = Ledger(db, TxnType.TRANSFER_COLLECTION, actor_id=actor.id, ref=ref, notes=notes)
    ledger.move(t.product_id, source, system_location(db, LocationType.TRANSIT), qty, reservation=reservation)
    if qty < t.quantity:
        ledger.release(reservation)
        _cover_destination(db, t, -(t.quantity - qty), actor_id=actor.id, event="TRANSFER_COVER_RELEASED",
                           reason="Short collection")
    t.qty_collected = qty
    t.collected_by_user_id = actor.id
    t.collected_at = _now()
    t.collected_from_name = collected_from_name
    t.status = TransferStatus.IN_TRANSIT
    db.flush()
    for data_url in photos or []:
        proofs.add_photo(db, actor, "transfer", t.id, data_url)
    source_req = replenishment.request_for_transfer(db, actor.id, transfer=t, qty=qty, source=source)
    t.source_request_id = source_req.id
    db.flush()
    record_audit(db, actor_id=actor.id, action="transfer.collect", entity_type="transfer", entity_id=t.id,
                 reseller_id=t.source_reseller_id,
                 summary=f"Collected {qty} on {t.number} from {source.code}; replacement {source_req.number} raised"
                         + (f" (handed over by {collected_from_name})" if collected_from_name else ""))
    product = db.get(Product, t.product_id)
    if _find_for_me(db, t):
        _arranged(db, t, "COLLECTED", actor.id)   # tells the dealer itself ("Good news … on its way")
    else:
        notify_users(db, reseller_users(db, t.destination_reseller_id), "Tyres are on their way to you",
                     f"{qty} × {product.tyre_label} ({t.number})", link=link(t), entity_type="transfer",
                     entity_id=t.id, exclude=actor.id)
    notify_users(db, reseller_users(db, t.source_reseller_id),
                 f"Collected; your replacement has been raised ({source_req.number})",
                 f"{qty} × {product.tyre_label} collected on {t.number}", link=f"/replenishment/{source_req.id}",
                 entity_type="replenishment_request", entity_id=source_req.id, exclude=actor.id)
    return t


def _find_for_me(db: Session, t: Transfer) -> bool:
    """Is this transfer arranged for a dealer's "Get this tyre for me" stock request?"""
    from app.modules.stock_requests.models import StockRequestLine  # stock requests import this module

    return db.execute(select(StockRequestLine.id).where(StockRequestLine.arranging_transfer_id == t.id)
                      .limit(1)).first() is not None


def receive(db: Session, actor: User, transfer_id: int, *, quantity: int | None = None,
            notes: str | None = None, received_by_name: str | None = None,
            photos: list[str] | None = None) -> Transfer:
    t = lock_transfer(db, transfer_id)
    if not actor.is_reseller_user and not role_has(actor.role, P.TRANSFER_EXECUTE):
        raise PermissionDeniedError("Missing permission: transfer.execute")
    # The receiving dealer can confirm. A sales rep asked to carry it is the only staff member who can; for older
    # transfers with nothing arranged, a Sales Rep who collected it is (or the dealer).
    if t.carried_by_user_id:
        carrier = t.carried_by_user_id
    else:
        collector = db.get(User, t.collected_by_user_id) if t.collected_by_user_id else None
        carrier = collector.id if collector and collector.role == Role.SALES_REP else None
    proofs.ensure_can_confirm(db, actor, reseller_id=t.destination_reseller_id, what="Transfer",
                              carried_by_user_id=carrier)
    received_by_name, notes = proofs.receipt_details(actor, received_by_name, notes)
    if t.status != TransferStatus.IN_TRANSIT:
        raise ConflictError(f"{t.number} is {t.status}")
    if via_warehouse(t) and t.warehouse_received_at is None:
        raise ConflictError(f"{t.number} goes via the warehouse: the warehouse records that it received and checked "
                            "the tyres before they are delivered", code="awaiting_warehouse_check")
    qty = t.qty_in_transit if quantity is None else quantity
    if qty < 0 or qty > t.qty_in_transit:
        raise BusinessRuleError(f"Received quantity must be 0–{t.qty_in_transit}")
    dest = db.get(Location, t.destination_location_id)
    if qty > 0:
        ledger = Ledger(db, TxnType.TRANSFER_RECEIPT, actor_id=actor.id, ref=Ref("transfer", t.id, t.number),
                        notes=notes)
        ledger.move(t.product_id, system_location(db, LocationType.TRANSIT), dest, qty)
        _cover_destination(db, t, -qty, delivered=qty, actor_id=actor.id, event="DELIVERED",
                           reason="Received via transfer")
    t.qty_received += qty
    t.received_by_user_id = actor.id
    t.received_at = _now()
    t.received_by_name = received_by_name
    t.receipt_notes = notes
    for data_url in photos or []:
        proofs.add_photo(db, actor, "transfer", t.id, data_url)
    t.status = TransferStatus.COMPLETED if t.qty_in_transit == 0 else TransferStatus.RECEIVED_WITH_DISCREPANCY
    db.flush()
    record_audit(db, actor_id=actor.id, action="transfer.receive", entity_type="transfer", entity_id=t.id,
                 reseller_id=t.destination_reseller_id,
                 summary=f"Received {qty} of {t.qty_collected} on {t.number} at {dest.code}"
                         + (f"; {t.qty_in_transit} unresolved" if t.qty_in_transit else ""))
    return t


def resolve(db: Session, actor: User, transfer_id: int, *, outcome: str, quantity: int, reason: str) -> Transfer:
    """Resolve in-transit quantity: RETURN_TO_SOURCE (explicit reversal), LOST, or LATE_DELIVERY."""
    t = lock_transfer(db, transfer_id)
    if t.status not in (TransferStatus.IN_TRANSIT, TransferStatus.RECEIVED_WITH_DISCREPANCY):
        raise ConflictError(f"{t.number} is {t.status}")
    if quantity <= 0 or quantity > t.qty_in_transit:
        raise BusinessRuleError(f"{t.qty_in_transit} unit(s) are unresolved on {t.number}")
    if outcome == "LOST" and not role_has(actor.role, P.INVENTORY_ADJUST):
        raise PermissionDeniedError("Missing permission: inventory.adjust")
    ref = Ref("transfer", t.id, t.number)
    transit = system_location(db, LocationType.TRANSIT)
    ledger = Ledger(db, TxnType.TRANSIT_RESOLUTION, actor_id=actor.id, approved_by_id=actor.id, ref=ref,
                    reason=f"{outcome}: {reason}")
    if outcome == "RETURN_TO_SOURCE":
        ledger.move(t.product_id, transit, db.get(Location, t.source_location_id), quantity)
        t.qty_returned += quantity
        cancelled = 0
        if t.source_request_id:
            source_req = db.get(ReplenishmentRequest, t.source_request_id)
            cancelled = replenishment.cancel_open_quantity(
                db, actor.id, source_req, quantity, f"Transfer stock returned to source: {reason}", ref,
                release_allocations=True)
        if cancelled < quantity:
            record_audit(db, actor_id=actor.id, action="transfer.return_excess", entity_type="transfer",
                         entity_id=t.id, reseller_id=t.source_reseller_id,
                         summary=f"{t.number}: {quantity - cancelled} returned unit(s) exceed the open replacement "
                                 "obligation (already replenished); source may be above target")
        _cover_destination(db, t, -quantity, actor_id=actor.id, event="TRANSFER_COVER_RELEASED", reason=reason)
    elif outcome == "LOST":
        ledger.move(t.product_id, transit, system_location(db, LocationType.ADJUSTMENT), quantity)
        t.qty_lost += quantity  # source obligation remains (A-004)
        _cover_destination(db, t, -quantity, actor_id=actor.id, event="TRANSFER_COVER_RELEASED", reason=reason)
    elif outcome == "LATE_DELIVERY":
        ledger.move(t.product_id, transit, db.get(Location, t.destination_location_id), quantity)
        t.qty_received += quantity
        _cover_destination(db, t, -quantity, delivered=quantity, actor_id=actor.id, event="DELIVERED",
                           reason=f"Late transfer delivery: {reason}")
    else:
        raise BusinessRuleError("Outcome must be RETURN_TO_SOURCE, LOST or LATE_DELIVERY")
    if t.qty_in_transit == 0:
        if t.qty_received == 0 and t.qty_lost == 0:
            t.status = TransferStatus.CANCELLED
            t.cancel_reason = f"Reversed after collection: {reason}"
            t.cancelled_by_user_id = actor.id
            t.cancelled_at = _now()
        else:
            t.status = TransferStatus.COMPLETED
    db.flush()
    record_audit(db, actor_id=actor.id, action="transfer.resolve", entity_type="transfer", entity_id=t.id,
                 reseller_id=t.destination_reseller_id, summary=f"{t.number}: {outcome} {quantity} ({reason})")
    return t


def list_transfers(db: Session, user: User, *, status: TransferStatus | None = None, reseller_id: int | None = None,
                   open_only: bool = False, limit: int = 200) -> list[Transfer]:
    stmt = select(Transfer)
    restricted = scoped_reseller_id(user)
    for rid in (restricted, reseller_id):
        if rid is not None:
            stmt = stmt.where(or_(Transfer.source_reseller_id == rid, Transfer.destination_reseller_id == rid))
    if status is not None:
        stmt = stmt.where(Transfer.status == status)
    if open_only:
        stmt = stmt.where(Transfer.status.in_([
            TransferStatus.REQUESTED.value, TransferStatus.APPROVED.value, TransferStatus.IN_TRANSIT.value,
            TransferStatus.RECEIVED_WITH_DISCREPANCY.value]))
    return list(db.execute(stmt.order_by(Transfer.id.desc()).limit(limit)).scalars())
