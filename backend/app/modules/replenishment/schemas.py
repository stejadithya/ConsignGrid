from datetime import date, datetime

from pydantic import BaseModel, Field

from app.modules.replenishment.models import (
    DeliveryStatus,
    Priority,
    ReplenishmentReason,
    ReplenishmentStatus,
)
from app.modules.stock_requests.approval import ApprovalIn


class RequestOut(BaseModel):
    id: int
    number: str
    reseller_id: int
    reseller_name: str | None
    location_id: int
    location_code: str | None
    product_id: int
    sku: str | None
    product_name: str | None
    reason: ReplenishmentReason
    origin_type: str | None
    origin_id: int | None
    origin_number: str | None
    sale_line_id: int | None
    transfer_id: int | None
    qty_required: int
    qty_allocated: int
    qty_in_transit: int
    qty_transfer_covered: int
    qty_delivered: int
    qty_cancelled: int
    qty_outstanding: int
    qty_awaiting_supply: int
    priority: Priority
    expected_date: date | None
    purchase_order_line_id: int | None
    status: ReplenishmentStatus
    notes: str | None
    created_at: datetime
    closed_at: datetime | None
    age_days: int
    raised_by: str | None = None          # who raised the request (e.g. the reseller user who reported the sale)
    raised_by_role: str | None = None
    first_supply: bool = False             # "Latest stock": a tyre this reseller location had never held
    # Fulfilment on the request (release 1.11). Approval and escalation details are staff only (None for dealers).
    awaiting_approval: bool = False        # raised by a dealer or sales rep, nothing approved yet
    auto_approved: bool = False            # a sale or transfer replacement that reserved stock by itself
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_method: str | None = None
    approval_contact: str | None = None
    approval_comments: str | None = None
    escalated_to_user_id: int | None = None
    escalated_to: str | None = None
    escalated_by: str | None = None
    escalated_at: datetime | None = None
    escalation_note: str | None = None
    ready: bool = False                    # picked and packed, waiting to ship
    ready_at: datetime | None = None
    ready_by: str | None = None


class EventOut(BaseModel):
    id: int
    event_type: str
    quantity: int | None
    reference_type: str | None
    reference_id: int | None
    reference_number: str | None
    reason: str | None
    actor_name: str | None
    occurred_at: datetime


class AllocationOut(BaseModel):
    id: int
    warehouse_location_id: int
    quantity: int
    dispatched_qty: int
    released_qty: int
    open_qty: int
    status: str
    created_at: datetime


class LinkedRequestOut(BaseModel):
    """Another dealer's replenishment request in a transfer chain (staff only)."""

    id: int
    number: str
    reseller_name: str
    status: str
    qty_awaiting_supply: int


class CoveringTransferOut(BaseModel):
    """A transfer that covers this request, and the replacement it raised for the dealer who gave the tyres."""

    id: int
    number: str
    status: str
    quantity: int
    source_reseller_name: str | None
    replacement: LinkedRequestOut | None


class RequestDetailOut(RequestOut):
    events: list[EventOut]
    allocations: list[AllocationOut]
    delivery_lines: list[dict]
    deliveries: list["DeliveryOut"] = []   # full shipments for this request (receipt details, delivery note)
    # Transfer chain, staff only (dealers never see other dealers): the transfers covering this request, and for a
    # replacement raised by a transfer, the request that transfer filled.
    covered_by_transfers: list[CoveringTransferOut] = []
    fills_request: LinkedRequestOut | None = None


class ManualRequestIn(BaseModel):
    location_id: int
    product_id: int
    quantity: int = Field(gt=0, le=10000)
    reason: str = Field(min_length=3, max_length=500)
    priority: Priority = Priority.NORMAL
    expected_date: date | None = None
    approver_note: str | None = Field(default=None, max_length=1000)   # dealer or rep request: for whoever approves


class GenerateShortfallsIn(BaseModel):
    reseller_id: int | None = None
    location_id: int | None = None


class AllocateIn(BaseModel):
    quantity: int | None = Field(default=None, gt=0)
    warehouse_location_id: int | None = None


class ApproveIn(BaseModel):
    quantity: int | None = Field(default=None, gt=0)
    warehouse_location_id: int | None = None
    approval: ApprovalIn


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class ShipIn(BaseModel):
    shipping_method: str = Field(default="COURIER", pattern="^(COURIER|SALES_REP)$")
    carrier: str | None = Field(default=None, max_length=100)
    tracking_number: str | None = Field(default=None, max_length=100)
    carried_by_user_id: int | None = None
    notes: str | None = Field(default=None, max_length=1000)
    quantity: int | None = Field(default=None, gt=0)


class ReleaseIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class CancelIn(BaseModel):
    quantity: int | None = Field(default=None, gt=0)
    reason: str = Field(min_length=3, max_length=500)


class PlanningIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    priority: Priority | None = None
    expected_date: date | None = None
    clear_expected_date: bool = False
    purchase_order_line_id: int | None = None


class ProposalOut(BaseModel):
    request_id: int
    request_number: str
    reseller_id: int
    reseller_name: str | None
    location_id: int
    location_code: str | None
    product_id: int
    sku: str | None
    priority: Priority
    created_at: datetime
    awaiting_supply: int
    proposed_qty: int


class ConfirmLine(BaseModel):
    request_id: int
    quantity: int = Field(gt=0)


class ConfirmAllocationsIn(BaseModel):
    warehouse_location_id: int | None = None
    lines: list[ConfirmLine] = Field(min_length=1)


class DispatchLineIn(BaseModel):
    request_id: int
    quantity: int | None = Field(default=None, gt=0)


class DispatchIn(BaseModel):
    to_location_id: int
    lines: list[DispatchLineIn] = Field(min_length=1)
    carrier_reference: str | None = Field(default=None, max_length=100)
    tracking_number: str | None = Field(default=None, max_length=100)
    shipping_address: str | None = Field(default=None, max_length=1000)
    notes: str | None = None
    shipping_method: str = Field(default="COURIER", pattern="^(COURIER|SALES_REP)$")
    carried_by_user_id: int | None = None


class ReceiveLineIn(BaseModel):
    line_id: int
    qty_received: int = Field(ge=0)


class ReceiveIn(BaseModel):
    lines: list[ReceiveLineIn] = Field(default_factory=list)
    notes: str | None = None
    delivered_on: date | None = None
    delivery_reference: str | None = Field(default=None, max_length=100)
    received_by_name: str | None = Field(default=None, max_length=120)
    photos: list[str] = Field(default_factory=list, max_length=3)   # compressed photos (data URLs) taken at drop-off


class ResolveIn(BaseModel):
    line_id: int
    outcome: str = Field(pattern="^(RETURN_TO_WAREHOUSE|LOST|LATE_DELIVERY)$")
    quantity: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)


class DeliveryLineOut(BaseModel):
    id: int
    request_id: int
    request_number: str | None
    product_id: int
    sku: str | None
    qty_dispatched: int
    qty_received: int
    qty_returned: int
    qty_lost: int
    qty_late_received: int
    qty_open: int


class DeliveryOut(BaseModel):
    id: int
    number: str
    from_location_id: int
    from_location_code: str | None
    to_location_id: int
    to_location_code: str | None
    reseller_id: int
    reseller_name: str | None
    status: DeliveryStatus
    carrier_reference: str | None
    dispatched_at: datetime
    dispatched_by: str | None
    received_at: datetime | None
    received_by: str | None
    notes: str | None
    lines: list[DeliveryLineOut]
    tracking_number: str | None = None
    shipping_address: str | None = None
    stock_request_id: int | None = None
    stock_request_number: str | None = None
    delivered_on: date | None = None
    delivery_reference: str | None = None
    receipt_notes: str | None = None
    shipping_method: str = "COURIER"
    carried_by_user_id: int | None = None
    carried_by: str | None = None
    note_emailed_at: datetime | None = None
    note_email_to: str | None = None
    note_email_error: str | None = None
    received_by_name: str | None = None
    photos: list[int] = []
    photos_retired: int = 0   # archived or deleted under the photo archiving setting


class CoverageOut(BaseModel):
    location_id: int
    product_id: int
    target: int | None
    auto_replenish: bool
    on_hand: int
    open_outstanding: int
    in_transit_replenishment: int
    inbound_transfers: int
    shortfall: int


RequestDetailOut.model_rebuild()
