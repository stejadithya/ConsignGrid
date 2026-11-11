from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ReplenishmentReason(StrEnum):
    SALE = "SALE"
    TRANSFER = "TRANSFER"
    TARGET_SHORTFALL = "TARGET_SHORTFALL"
    MANUAL = "MANUAL"
    STOCK_REQUEST = "STOCK_REQUEST"  # an approved line of a consignment stock request


class ReplenishmentStatus(StrEnum):
    OPEN = "OPEN"
    PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
    ALLOCATED = "ALLOCATED"
    IN_TRANSIT = "IN_TRANSIT"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


OPEN_STATUSES = (
    ReplenishmentStatus.OPEN, ReplenishmentStatus.PARTIALLY_FULFILLED,
    ReplenishmentStatus.ALLOCATED, ReplenishmentStatus.IN_TRANSIT,
)


class Priority(StrEnum):
    URGENT = "URGENT"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


PRIORITY_RANK = {Priority.URGENT: 0, Priority.HIGH: 1, Priority.NORMAL: 2, Priority.LOW: 3}


class ReplenishmentRequest(Base):
    """Demand to deliver stock to a reseller location. The awaiting-supply portion is the backorder."""

    __tablename__ = "replenishment_requests"
    __table_args__ = (
        CheckConstraint("qty_required > 0", name="required_positive"),
        CheckConstraint(
            "qty_allocated >= 0 AND qty_in_transit >= 0 AND qty_transfer_covered >= 0 "
            "AND qty_delivered >= 0 AND qty_cancelled >= 0",
            name="quantities_non_negative",
        ),
        CheckConstraint(
            "qty_allocated + qty_in_transit + qty_transfer_covered + qty_delivered + qty_cancelled <= qty_required",
            name="quantities_within_required",
        ),
        Index("ix_replenishment_requests_loc_prod", "location_id", "product_id"),
        Index("ix_replenishment_requests_origin", "origin_type", "origin_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    reseller_id: Mapped[int] = mapped_column(ForeignKey("resellers.id"), nullable=False, index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    reason: Mapped[ReplenishmentReason] = mapped_column(
        Enum(ReplenishmentReason, name="replenishment_reason", native_enum=False, length=20), nullable=False
    )
    origin_type: Mapped[str | None] = mapped_column(String(40))
    origin_id: Mapped[int | None] = mapped_column()
    origin_number: Mapped[str | None] = mapped_column(String(30))
    sale_line_id: Mapped[int | None] = mapped_column(ForeignKey("consignment_sale_lines.id"), index=True)
    transfer_id: Mapped[int | None] = mapped_column(ForeignKey("transfers.id", use_alter=True), index=True)
    qty_required: Mapped[int] = mapped_column(nullable=False)
    qty_allocated: Mapped[int] = mapped_column(nullable=False, default=0)
    qty_in_transit: Mapped[int] = mapped_column(nullable=False, default=0)
    # Covered by an approved / in-transit inter-reseller transfer linked to this request.
    qty_transfer_covered: Mapped[int] = mapped_column(nullable=False, default=0)
    qty_delivered: Mapped[int] = mapped_column(nullable=False, default=0)
    qty_cancelled: Mapped[int] = mapped_column(nullable=False, default=0)
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="priority", native_enum=False, length=10), nullable=False, default=Priority.NORMAL
    )
    expected_date: Mapped[date | None] = mapped_column(Date)
    purchase_order_line_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_order_lines.id"))
    status: Mapped[ReplenishmentStatus] = mapped_column(
        Enum(ReplenishmentStatus, name="replenishment_status", native_enum=False, length=20),
        nullable=False, default=ReplenishmentStatus.OPEN, index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The reseller location had never held this tyre when the request was raised: shown as "Latest stock".
    first_supply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Fulfilment on the request itself (release 1.11, finding 22): approval details, escalation to a Relationship
    # Manager, and "picked and packed". Staff only; never shown to dealers.
    approval_method: Mapped[str | None] = mapped_column(String(20))
    approval_contact: Mapped[str | None] = mapped_column(String(200))
    approval_comments: Mapped[str | None] = mapped_column(Text)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    escalated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_note: Mapped[str | None] = mapped_column(Text)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    events: Mapped[list["ReplenishmentEvent"]] = relationship(order_by="ReplenishmentEvent.id")

    @property
    def qty_outstanding(self) -> int:
        return self.qty_required - self.qty_delivered - self.qty_cancelled

    @property
    def qty_awaiting_supply(self) -> int:
        return self.qty_outstanding - self.qty_allocated - self.qty_in_transit - self.qty_transfer_covered

    def derive_status(self) -> ReplenishmentStatus:
        if self.qty_cancelled == self.qty_required:
            return ReplenishmentStatus.CANCELLED
        if self.qty_outstanding == 0:
            return ReplenishmentStatus.FULFILLED
        if self.qty_in_transit > 0:
            return ReplenishmentStatus.IN_TRANSIT
        if self.qty_allocated > 0 or self.qty_transfer_covered > 0:
            return ReplenishmentStatus.ALLOCATED
        if self.qty_delivered > 0:
            return ReplenishmentStatus.PARTIALLY_FULFILLED
        return ReplenishmentStatus.OPEN


class ReplenishmentEvent(Base):
    """Append-only history of what happened to a request (each partial fulfilment individually)."""

    __tablename__ = "replenishment_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("replenishment_requests.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity: Mapped[int | None] = mapped_column()
    reference_type: Mapped[str | None] = mapped_column(String(40))
    reference_id: Mapped[int | None] = mapped_column()
    reference_number: Mapped[str | None] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AllocationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISPATCHED = "DISPATCHED"
    RELEASED = "RELEASED"
    CLOSED = "CLOSED"


class ReplenishmentAllocation(Base):
    """Warehouse stock reserved for a request."""

    __tablename__ = "replenishment_allocations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("dispatched_qty >= 0 AND released_qty >= 0", name="non_negative"),
        CheckConstraint("dispatched_qty + released_qty <= quantity", name="within_quantity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("replenishment_requests.id"), nullable=False, index=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stock_reservations.id"), nullable=False)
    warehouse_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    dispatched_qty: Mapped[int] = mapped_column(nullable=False, default=0)
    released_qty: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[AllocationStatus] = mapped_column(
        Enum(AllocationStatus, name="allocation_status", native_enum=False, length=20),
        nullable=False, default=AllocationStatus.ACTIVE,
    )
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    @property
    def open_qty(self) -> int:
        return self.quantity - self.dispatched_qty - self.released_qty


class DeliveryStatus(StrEnum):
    IN_TRANSIT = "IN_TRANSIT"
    RECEIVED = "RECEIVED"
    RECEIVED_WITH_DISCREPANCY = "RECEIVED_WITH_DISCREPANCY"
    CLOSED = "CLOSED"  # discrepancy fully resolved


class Delivery(Base):
    """A replenishment dispatch from a warehouse to one reseller location."""

    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    from_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    to_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    reseller_id: Mapped[int] = mapped_column(ForeignKey("resellers.id"), nullable=False, index=True)
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="delivery_status", native_enum=False, length=30),
        nullable=False, default=DeliveryStatus.IN_TRANSIT, index=True,
    )
    carrier_reference: Mapped[str | None] = mapped_column(String(100))  # carrier / courier
    tracking_number: Mapped[str | None] = mapped_column(String(100))
    shipping_address: Mapped[str | None] = mapped_column(Text)
    stock_request_id: Mapped[int | None] = mapped_column(ForeignKey("stock_requests.id", use_alter=True), index=True)
    # How the tyres travel: COURIER (carrier + tracking) or SALES_REP (a sales representative carries them).
    shipping_method: Mapped[str] = mapped_column(String(20), nullable=False, default="COURIER", server_default="COURIER")
    carried_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # Delivery note email to the reseller after receipt.
    note_emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note_email_to: Mapped[str | None] = mapped_column(String(255))
    note_email_error: Mapped[str | None] = mapped_column(Text)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    dispatched_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    received_by_name: Mapped[str | None] = mapped_column(String(120))   # the person at the dealer who took it
    delivered_on: Mapped[date | None] = mapped_column(Date)
    delivery_reference: Mapped[str | None] = mapped_column(String(100))  # proof-of-delivery / docket number
    receipt_notes: Mapped[str | None] = mapped_column(Text)
    dispatch_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_transactions.id"))
    notes: Mapped[str | None] = mapped_column(Text)

    lines: Mapped[list["DeliveryLine"]] = relationship(order_by="DeliveryLine.id")


class DeliveryLine(Base):
    __tablename__ = "delivery_lines"
    __table_args__ = (
        CheckConstraint("qty_dispatched > 0", name="dispatched_positive"),
        CheckConstraint(
            "qty_received >= 0 AND qty_returned >= 0 AND qty_lost >= 0 AND qty_late_received >= 0",
            name="non_negative",
        ),
        CheckConstraint(
            "qty_received + qty_returned + qty_lost + qty_late_received <= qty_dispatched", name="within_dispatched"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id"), nullable=False, index=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("replenishment_requests.id"), nullable=False, index=True)
    allocation_id: Mapped[int] = mapped_column(ForeignKey("replenishment_allocations.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    qty_dispatched: Mapped[int] = mapped_column(nullable=False)
    qty_received: Mapped[int] = mapped_column(nullable=False, default=0)
    qty_returned: Mapped[int] = mapped_column(nullable=False, default=0)
    qty_lost: Mapped[int] = mapped_column(nullable=False, default=0)
    qty_late_received: Mapped[int] = mapped_column(nullable=False, default=0)

    @property
    def qty_open(self) -> int:
        """Still in transit and unresolved."""
        return self.qty_dispatched - self.qty_received - self.qty_returned - self.qty_lost - self.qty_late_received
