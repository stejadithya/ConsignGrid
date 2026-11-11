from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from app.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.core.lookups import Names
from app.core.permissions import P, Role
from app.modules.delivery_notes import service as delivery_notes
from app.modules.identity.deps import DB, require
from app.modules.identity.models import User
from app.modules.proofs import service as proofs
from app.modules.replenishment.models import Priority, ReplenishmentRequest
from app.modules.transfers import service
from app.modules.transfers.models import Transfer, TransferStatus

router = APIRouter(prefix="/transfers", tags=["transfers"])
Reader = Annotated[User, Depends(require(P.TRANSFER_READ))]


class TransferRequestIn(BaseModel):
    destination_location_id: int | None
    product_id: int
    quantity: int = Field(gt=0, le=1000)
    reason: str = Field(min_length=3, max_length=500)
    urgency: Priority = Priority.HIGH
    destination_request_id: int | None = None
    notes: str | None = None


class ShippingIn(BaseModel):
    """How the tyres travel from the source dealer to the destination (finding 23)."""

    shipping_method: str = Field(pattern="^(COURIER|SALES_REP)$")
    carrier_reference: str | None = Field(default=None, max_length=100)
    tracking_number: str | None = Field(default=None, max_length=100)
    carried_by_user_id: int | None = None
    route: str = Field(default="DIRECT", pattern="^(DIRECT|VIA_WAREHOUSE)$")   # via the warehouse to be checked


class ApproveIn(BaseModel):
    source_location_id: int
    approval_notes: str | None = Field(default=None, max_length=1000)
    source_consent_reference: str | None = Field(default=None, max_length=200)
    shipping: ShippingIn | None = None   # optional: arrange the pick-up in the same step


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class QtyIn(BaseModel):
    quantity: int | None = Field(default=None, ge=0)
    notes: str | None = None


class CollectIn(QtyIn):
    collected_from_name: str | None = Field(default=None, max_length=120)   # required when a sales rep collects
    photos: list[str] = Field(default_factory=list, max_length=3)


class WarehouseReceiptIn(BaseModel):
    notes: str = Field(min_length=3, max_length=2000)    # how many arrived and their condition
    photos: list[str] = Field(default_factory=list, max_length=3)


class ReceiveIn(QtyIn):
    received_by_name: str | None = Field(default=None, max_length=120)
    photos: list[str] = Field(default_factory=list, max_length=3)   # compressed photos (data URLs) taken at drop-off


class ResolveIn(BaseModel):
    outcome: str = Field(pattern="^(RETURN_TO_SOURCE|LOST|LATE_DELIVERY)$")
    quantity: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)


class LinkedReq(BaseModel):
    id: int
    number: str
    status: str
    qty_required: int
    qty_outstanding: int
    qty_awaiting_supply: int


class TransferOut(BaseModel):
    id: int
    number: str
    product_id: int
    sku: str | None
    product_name: str | None
    quantity: int
    destination_location_id: int
    destination_location_code: str | None
    destination_reseller_id: int | None
    destination_reseller_name: str | None
    source_location_id: int | None
    source_location_code: str | None
    source_reseller_id: int | None
    source_reseller_name: str | None
    reason: str
    urgency: Priority
    status: TransferStatus
    requested_by: str | None
    requested_at: datetime
    approved_by: str | None
    approved_at: datetime | None
    approval_notes: str | None
    source_consent_reference: str | None
    collected_by: str | None
    collected_at: datetime | None
    qty_collected: int
    received_by: str | None
    received_at: datetime | None
    qty_received: int
    qty_returned: int
    qty_lost: int
    qty_in_transit: int
    destination_request: LinkedReq | None
    source_request: LinkedReq | None
    cancel_reason: str | None
    notes: str | None
    collected_by_user_id: int | None = None
    collected_by_sales_rep: bool = False
    received_by_name: str | None = None
    receipt_notes: str | None = None
    photos: list[int] = []
    photos_retired: int = 0
    shipping_method: str | None = None
    carrier_reference: str | None = None
    tracking_number: str | None = None
    carried_by_user_id: int | None = None
    carried_by: str | None = None
    shipping_arranged_at: datetime | None = None
    shipping_arranged_by: str | None = None
    collected_from_name: str | None = None
    note_emailed_at: datetime | None = None
    note_email_to: str | None = None
    note_email_error: str | None = None
    route: str = "DIRECT"                         # DIRECT or VIA_WAREHOUSE
    warehouse_received_at: datetime | None = None
    warehouse_received_by: str | None = None
    warehouse_check_notes: str | None = None


class SourceOut(BaseModel):
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
    transfer_consent: str
    eligible: bool
    ineligible_reason: str | None


class SourcesOut(BaseModel):
    product_id: int
    warehouse_available: int
    sources: list[SourceOut]


def _linked(db, req_id) -> LinkedReq | None:
    if req_id is None:
        return None
    r = db.get(ReplenishmentRequest, req_id)
    return LinkedReq(id=r.id, number=r.number, status=r.status, qty_required=r.qty_required,
                     qty_outstanding=r.qty_outstanding, qty_awaiting_supply=r.qty_awaiting_supply)


OTHER_RESELLER = "Another dealer"


def _redact_counterparty(out: TransferOut, reseller_id: int) -> TransferOut:
    """Reseller users see their own side of a transfer only; the other party is not disclosed."""
    if out.source_reseller_id is not None and out.source_reseller_id != reseller_id:
        out.source_reseller_id = out.source_location_id = None
        out.source_reseller_name, out.source_location_code = OTHER_RESELLER, None
        out.source_request = None
        out.collected_from_name = None   # a person at the other dealer
    out.warehouse_check_notes = None     # internal
    if out.destination_reseller_id != reseller_id:
        out.destination_reseller_id = out.destination_location_id = None
        out.destination_reseller_name, out.destination_location_code = OTHER_RESELLER, None
        out.destination_request = None
    return out


def transfers_out(db, transfers: list[Transfer], user: User | None = None) -> list[TransferOut]:
    names = Names(db)
    for t in transfers:
        names.add("product", t.product_id).add("location", t.destination_location_id, t.source_location_id)
        names.add("reseller", t.destination_reseller_id, t.source_reseller_id)
        names.add("user", t.requested_by_user_id, t.approved_by_user_id, t.collected_by_user_id, t.received_by_user_id,
                  t.carried_by_user_id, t.shipping_arranged_by_user_id, t.warehouse_received_by_user_id)
    names.resolve()
    photos = proofs.photo_ids(db, "transfer", [t.id for t in transfers])
    retired = proofs.retired_counts(db, "transfer", [t.id for t in transfers])
    out = [
        TransferOut(
            id=t.id, number=t.number, product_id=t.product_id, sku=names.sku(t.product_id),
            product_name=names.product_name(t.product_id), quantity=t.quantity,
            destination_location_id=t.destination_location_id,
            destination_location_code=names.loc_code(t.destination_location_id),
            destination_reseller_id=t.destination_reseller_id,
            destination_reseller_name=names.reseller_name(t.destination_reseller_id),
            source_location_id=t.source_location_id, source_location_code=names.loc_code(t.source_location_id),
            source_reseller_id=t.source_reseller_id, source_reseller_name=names.reseller_name(t.source_reseller_id),
            reason=t.reason, urgency=t.urgency, status=t.status, requested_by=names.user_name(t.requested_by_user_id),
            requested_at=t.requested_at, approved_by=names.user_name(t.approved_by_user_id), approved_at=t.approved_at,
            approval_notes=t.approval_notes, source_consent_reference=t.source_consent_reference,
            collected_by=names.user_name(t.collected_by_user_id), collected_at=t.collected_at,
            qty_collected=t.qty_collected, received_by=names.user_name(t.received_by_user_id),
            received_at=t.received_at, qty_received=t.qty_received, qty_returned=t.qty_returned, qty_lost=t.qty_lost,
            qty_in_transit=t.qty_in_transit, destination_request=_linked(db, t.destination_request_id),
            source_request=_linked(db, t.source_request_id), cancel_reason=t.cancel_reason, notes=t.notes,
            collected_by_user_id=t.collected_by_user_id,
            collected_by_sales_rep=bool(t.collected_by_user_id and names.users.get(t.collected_by_user_id)
                                        and names.users[t.collected_by_user_id].role == Role.SALES_REP),
            received_by_name=t.received_by_name, receipt_notes=t.receipt_notes, photos=photos.get(t.id, []),
            photos_retired=retired.get(t.id, 0), shipping_method=t.shipping_method,
            carrier_reference=t.carrier_reference, tracking_number=t.tracking_number,
            carried_by_user_id=t.carried_by_user_id, carried_by=names.user_name(t.carried_by_user_id),
            shipping_arranged_at=t.shipping_arranged_at, shipping_arranged_by=names.user_name(t.shipping_arranged_by_user_id),
            collected_from_name=t.collected_from_name, note_emailed_at=t.note_emailed_at, note_email_to=t.note_email_to,
            note_email_error=t.note_email_error, route=t.route or "DIRECT", warehouse_received_at=t.warehouse_received_at,
            warehouse_received_by=names.user_name(t.warehouse_received_by_user_id),
            warehouse_check_notes=t.warehouse_check_notes,
        )
        for t in transfers
    ]
    if user is not None and user.is_reseller_user:
        out = [_redact_counterparty(o, user.reseller_id) for o in out]
    return out


@router.get("", response_model=list[TransferOut])
def list_transfers(db: DB, user: Reader, status: TransferStatus | None = None, reseller_id: int | None = None,
                   open_only: bool = False):
    return transfers_out(db, service.list_transfers(db, user, status=status, reseller_id=reseller_id,
                                                    open_only=open_only), user)


@router.get("/sources", response_model=SourcesOut)
def sources(product_id: int, db: DB, user: Reader, exclude_location_id: int | None = None, quantity: int = 1):
    if user.is_reseller_user:
        raise PermissionDeniedError("Not available to dealer users")
    wh, opts = service.find_sources(db, product_id, exclude_location_id=exclude_location_id, quantity=quantity)
    return SourcesOut(product_id=product_id, warehouse_available=wh, sources=[SourceOut(**o.__dict__) for o in opts])


@router.get("/{transfer_id}", response_model=TransferOut)
def get_transfer(transfer_id: int, db: DB, user: Reader):
    return transfers_out(db, [service.get_transfer(db, user, transfer_id)], user)[0]


@router.post("", response_model=TransferOut, status_code=201)
def request_transfer(data: TransferRequestIn, db: DB, user: Annotated[User, Depends(require(P.TRANSFER_REQUEST))]):
    t = service.request_transfer(db, user, **data.model_dump())
    db.commit()
    return transfers_out(db, [t])[0]


@router.post("/{transfer_id}/approve", response_model=TransferOut)
def approve(transfer_id: int, data: ApproveIn, db: DB, user: Annotated[User, Depends(require(P.TRANSFER_APPROVE))]):
    t = service.approve(db, user, transfer_id, **data.model_dump(exclude={"shipping"}))
    if data.shipping is not None:
        t = service.arrange_shipping(db, user, transfer_id, **data.shipping.model_dump())
    db.commit()
    return transfers_out(db, [t])[0]


@router.post("/{transfer_id}/reject", response_model=TransferOut)
def reject(transfer_id: int, data: ReasonIn, db: DB, user: Annotated[User, Depends(require(P.TRANSFER_APPROVE))]):
    t = service.reject(db, user, transfer_id, data.reason)
    db.commit()
    return transfers_out(db, [t])[0]


@router.post("/{transfer_id}/cancel", response_model=TransferOut)
def cancel(transfer_id: int, data: ReasonIn, db: DB, user: Annotated[User, Depends(require(P.TRANSFER_APPROVE))]):
    t = service.cancel(db, user, transfer_id, data.reason)
    db.commit()
    return transfers_out(db, [t])[0]


@router.post("/{transfer_id}/shipping", response_model=TransferOut)
def shipping(transfer_id: int, data: ShippingIn, db: DB, user: Annotated[User, Depends(require(P.TRANSFER_APPROVE))]):
    t = service.arrange_shipping(db, user, transfer_id, **data.model_dump())
    db.commit()
    return transfers_out(db, [t])[0]


@router.post("/{transfer_id}/warehouse-receipt", response_model=TransferOut)
def warehouse_receipt(transfer_id: int, data: WarehouseReceiptIn, db: DB,
                      user: Annotated[User, Depends(require(P.TRANSFER_APPROVE))]):
    """Via-warehouse transfers: the warehouse received and checked the tyres; the Sales Rep can now deliver them."""
    t = service.warehouse_receive(db, user, transfer_id, notes=data.notes, photos=data.photos)
    db.commit()
    return transfers_out(db, [t])[0]


@router.post("/{transfer_id}/collect", response_model=TransferOut)
def collect(transfer_id: int, data: CollectIn, db: DB, user: Annotated[User, Depends(require(P.TRANSFER_EXECUTE))]):
    t = service.collect(db, user, transfer_id, quantity=data.quantity, notes=data.notes,
                        collected_from_name=data.collected_from_name, photos=data.photos)
    db.commit()
    return transfers_out(db, [t])[0]


@router.post("/{transfer_id}/receive", response_model=TransferOut)
def receive(transfer_id: int, data: ReceiveIn, db: DB, user: Reader):
    """Confirm arrival: staff who move transfers, or the receiving dealer (rules in proofs.ensure_can_confirm)."""
    service.receive(db, user, transfer_id, quantity=data.quantity, notes=data.notes,
                    received_by_name=data.received_by_name, photos=data.photos)
    db.commit()
    delivery_notes.send_after_transfer_receipt(db, transfer_id)
    return transfers_out(db, [db.get(Transfer, transfer_id)])[0]


def _note_transfer(db, user: User, transfer_id: int) -> Transfer:
    """Staff, or the destination dealer: the note names the destination, so the source dealer cannot open it."""
    t = service.get_transfer(db, user, transfer_id)
    if user.is_reseller_user and user.reseller_id != t.destination_reseller_id:
        raise NotFoundError("Transfer not found")
    return t


@router.get("/{transfer_id}/delivery-note.pdf")
def delivery_note_pdf(transfer_id: int, db: DB, user: Reader):
    t = _note_transfer(db, user, transfer_id)
    pdf = delivery_notes.render_pdf(delivery_notes.note_data_for_transfer(db, t))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="Delivery-note-{t.number}.pdf"'})


@router.post("/{transfer_id}/email-delivery-note")
def email_delivery_note(transfer_id: int, db: DB, user: Annotated[User, Depends(require(P.TRANSFER_APPROVE))]):
    """Send (or resend) the transfer's delivery note to the destination dealer's email address."""
    t = _note_transfer(db, user, transfer_id)
    if t.received_at is None:
        raise BusinessRuleError("The delivery note is emailed once the transfer has been received")
    status = delivery_notes.send_for_transfer(db, t)
    db.commit()
    return {"status": status, "transfer": transfers_out(db, [t], user)[0]}


@router.post("/{transfer_id}/resolve", response_model=TransferOut)
def resolve(transfer_id: int, data: ResolveIn, db: DB, user: Annotated[User, Depends(require(P.TRANSFER_APPROVE))]):
    t = service.resolve(db, user, transfer_id, outcome=data.outcome, quantity=data.quantity, reason=data.reason)
    db.commit()
    return transfers_out(db, [t])[0]
