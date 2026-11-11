from datetime import date, datetime

from pydantic import BaseModel, Field

from app.modules.replenishment.models import Priority
from app.modules.replenishment.schemas import DeliveryOut
from app.modules.stock_requests.approval import ApprovalIn  # noqa: F401  (re-exported: shared with replenishment)
from app.modules.stock_requests.models import RemainderAction, StockRequestStatus


class LineIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=500)
    find_for_me: bool = False   # "Get this tyre for me": the warehouse finds what it cannot supply


class SupplyCheckLineIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)


class SupplyCheckIn(BaseModel):
    lines: list[SupplyCheckLineIn] = Field(min_length=1, max_length=100)


class SupplyCheckOut(BaseModel):
    product_id: int
    needs_help: bool   # the warehouse cannot cover the full quantity right now (no quantities are disclosed)


class StockRequestIn(BaseModel):
    location_id: int
    lines: list[LineIn] = Field(min_length=1)
    priority: Priority = Priority.NORMAL
    required_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    shipping_address: str | None = Field(default=None, max_length=1000)
    submit: bool = False


class StockRequestUpdate(BaseModel):
    lines: list[LineIn] = Field(min_length=1)
    priority: Priority = Priority.NORMAL
    required_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    shipping_address: str | None = Field(default=None, max_length=1000)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class DecisionLineIn(BaseModel):
    line_id: int
    approve_qty: int = Field(ge=0)
    remainder: RemainderAction = RemainderAction.BACKORDER
    notes: str | None = Field(default=None, max_length=500)


class DecisionIn(BaseModel):
    lines: list[DecisionLineIn] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=2000)
    # Required whenever anything is approved or backordered.
    approval: ApprovalIn | None = None


class ReserveIn(BaseModel):
    quantity: int | None = Field(default=None, gt=0)


class ReleaseIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    to_backorder: bool = False


class ShipLineIn(BaseModel):
    line_id: int
    quantity: int = Field(ge=0)


class ShipIn(BaseModel):
    shipping_method: str = Field(default="COURIER", pattern="^(COURIER|SALES_REP)$")
    carrier: str | None = Field(default=None, max_length=100)   # required for COURIER
    carried_by_user_id: int | None = None                        # required for SALES_REP
    tracking_number: str | None = Field(default=None, max_length=100)
    shipping_address: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[ShipLineIn] | None = None


class ConfirmLineIn(BaseModel):
    line_id: int   # delivery line id
    qty_received: int = Field(ge=0)


class ConfirmDeliveryIn(BaseModel):
    lines: list[ConfirmLineIn] = Field(default_factory=list)
    delivered_on: date | None = None
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    received_by_name: str | None = Field(default=None, max_length=120)
    photos: list[str] = Field(default_factory=list, max_length=3)   # compressed photos (data URLs) taken at drop-off


class StockRequestOut(BaseModel):
    id: int
    number: str
    reseller_id: int
    reseller_name: str | None
    location_id: int
    location_code: str | None
    status: StockRequestStatus
    decision: StockRequestStatus | None
    priority: Priority
    required_date: date | None
    notes: str | None
    shipping_address: str | None
    created_by: str | None
    created_by_user_id: int
    created_by_role: str
    created_at: datetime
    submitted_at: datetime | None
    reviewed_by: str | None
    reviewed_by_role: str | None
    reviewed_at: datetime | None
    review_notes: str | None
    ready_at: datetime | None
    closed_at: datetime | None
    line_count: int
    qty_requested: int
    qty_approved: int
    qty_rejected: int
    qty_backordered: int
    qty_reserved: int
    qty_shipped: int
    qty_delivered: int
    # Waiting for a Relationship Manager (staff only; None for dealer users).
    escalated_to_user_id: int | None = None
    escalated_to: str | None = None
    escalated_by: str | None = None
    escalated_at: datetime | None = None
    escalation_note: str | None = None


class EscalateIn(BaseModel):
    to_user_id: int
    note: str | None = Field(default=None, max_length=1000)


class CallbackIn(BaseModel):
    preferred_time: str = Field(min_length=2, max_length=200)   # e.g. "Tomorrow morning"
    phone: str = Field(min_length=3, max_length=50)


class HandBackIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class LineOut(BaseModel):
    id: int
    line_no: int
    product_id: int
    sku: str | None
    product_name: str | None
    product_active: bool
    qty_requested: int
    qty_approved: int
    qty_rejected: int
    qty_backordered: int
    qty_released: int
    qty_reserved: int
    qty_in_transit: int
    qty_shipped: int
    qty_delivered: int
    qty_backorder_open: int
    notes: str | None
    decision_notes: str | None
    replenishment_request_id: int | None
    replenishment_number: str | None
    warehouse_available: int | None = None
    first_supply: bool = False   # "Latest stock": the reseller had never held this tyre
    find_for_me: bool = False
    qty_arranging: int = 0                       # handed to the warehouse to find from another dealer
    arranging_transfer_id: int | None = None
    arranging_transfer_number: str | None = None
    # What this dealer already holds of the tyre (staff only; None for dealer users): this shop / all shops.
    dealer_on_hand: int | None = None
    dealer_on_hand_all: int | None = None
    # Transfers from another dealer covering this line's backorder (staff only, UAT round 2).
    covering_transfers: list[dict] = []


class EventOut(BaseModel):
    id: int
    action: str
    from_status: str | None
    to_status: str | None
    summary: str
    details: dict | None
    actor_name: str | None
    actor_role: str | None
    occurred_at: datetime


class StockRequestDetailOut(StockRequestOut):
    lines: list[LineOut]
    events: list[EventOut]
    shipments: list[DeliveryOut]
    # Staff only (None for dealer users).
    approval_method: str | None = None
    approval_contact: str | None = None
    approval_comments: str | None = None


class InventoryRow(BaseModel):
    product_id: int
    sku: str
    product_name: str
    is_active: bool
    warehouse_on_hand: int
    blocked: int
    reserved: int
    shipped: int
    total: int
    available: int
    delivered: int
    requested_pending: int


class AllocationRow(BaseModel):
    allocation_id: int
    product_id: int
    sku: str | None
    product_name: str | None
    reseller_id: int
    reseller_name: str | None
    location_code: str | None
    quantity: int
    open_qty: int
    replenishment_request_id: int
    replenishment_number: str
    stock_request_id: int | None
    stock_request_number: str | None
    created_at: datetime


class NotificationOut(BaseModel):
    id: int
    title: str
    body: str | None
    link: str | None
    entity_type: str | None
    entity_id: int | None
    read_at: datetime | None
    created_at: datetime
