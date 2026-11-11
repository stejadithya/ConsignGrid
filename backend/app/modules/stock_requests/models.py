"""Consignment stock requests: a multi-SKU request with a Central Team approval stage.

Approved lines become replenishment requests (one per SKU), so reservation, dispatch, delivery and
backorders reuse the existing replenishment workflow and ledger. See docs/STOCK_REQUESTS.md.
"""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.modules.replenishment.models import Priority


class StockRequestStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    PARTIALLY_APPROVED = "PARTIALLY_APPROVED"
    REJECTED = "REJECTED"
    READY_FOR_SHIPMENT = "READY_FOR_SHIPMENT"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


PENDING_STATUSES = (StockRequestStatus.SUBMITTED, StockRequestStatus.UNDER_REVIEW)
EDITABLE_STATUSES = (StockRequestStatus.DRAFT,)
# Approved in some form: fulfilment follows the linked replenishment requests.
FULFILMENT_STATUSES = (
    StockRequestStatus.APPROVED, StockRequestStatus.PARTIALLY_APPROVED, StockRequestStatus.READY_FOR_SHIPMENT,
    StockRequestStatus.SHIPPED, StockRequestStatus.DELIVERED,
)


class RemainderAction(StrEnum):
    """What happens to the requested quantity that is not approved now."""

    BACKORDER = "BACKORDER"
    REJECT = "REJECT"
    # Backorder it and arrange it now from another dealer: a transfer request linked to the backorder (UAT round 2).
    TRANSFER = "TRANSFER"


class ApprovalMethod(StrEnum):
    """How an approval was agreed (finding 17)."""

    PHONE = "PHONE"
    IN_PERSON = "IN_PERSON"
    EMAIL = "EMAIL"
    TEXT = "TEXT"            # text message or WhatsApp
    STANDARD = "STANDARD"    # standard approval, no contact needed


class StockRequest(TimestampMixin, Base):
    __tablename__ = "stock_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    reseller_id: Mapped[int] = mapped_column(ForeignKey("resellers.id"), nullable=False, index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    status: Mapped[StockRequestStatus] = mapped_column(
        Enum(StockRequestStatus, name="stock_request_status", native_enum=False, length=30),
        nullable=False, default=StockRequestStatus.DRAFT, index=True,
    )
    # The approval outcome (APPROVED / PARTIALLY_APPROVED / REJECTED), kept while fulfilment moves status on.
    decision: Mapped[StockRequestStatus | None] = mapped_column(
        Enum(StockRequestStatus, name="stock_request_status", native_enum=False, length=30)
    )
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="priority", native_enum=False, length=10), nullable=False, default=Priority.NORMAL
    )
    required_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    shipping_address: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_by_role: Mapped[str] = mapped_column(String(30), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_by_role: Mapped[str | None] = mapped_column(String(30))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
    # Approval details (finding 17): how it was agreed, who was spoken to, comments.
    approval_method: Mapped[str | None] = mapped_column(String(20))
    approval_contact: Mapped[str | None] = mapped_column(String(200))
    approval_comments: Mapped[str | None] = mapped_column(Text)
    # Sent to a Relationship Manager for approval (finding 18, D10). Cleared by "hand back".
    escalated_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    escalated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_note: Mapped[str | None] = mapped_column(Text)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list["StockRequestLine"]] = relationship(order_by="StockRequestLine.line_no",
                                                           cascade="all, delete-orphan")


class StockRequestLine(Base):
    __tablename__ = "stock_request_lines"
    __table_args__ = (
        CheckConstraint("qty_requested > 0", name="requested_positive"),
        CheckConstraint("qty_approved >= 0 AND qty_rejected >= 0 AND qty_backordered >= 0 AND qty_released >= 0",
                        name="non_negative"),
        CheckConstraint("qty_approved + qty_rejected + qty_backordered + qty_arranging <= qty_requested",
                        name="within_requested"),
        CheckConstraint("qty_arranging >= 0", name="arranging_non_negative"),
        CheckConstraint("qty_released <= qty_approved", name="released_within_approved"),
        UniqueConstraint("stock_request_id", "product_id", name="one_line_per_product"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_request_id: Mapped[int] = mapped_column(ForeignKey("stock_requests.id", ondelete="CASCADE"),
                                                  nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    qty_requested: Mapped[int] = mapped_column(nullable=False)
    qty_approved: Mapped[int] = mapped_column(nullable=False, default=0)
    qty_rejected: Mapped[int] = mapped_column(nullable=False, default=0)
    qty_backordered: Mapped[int] = mapped_column(nullable=False, default=0)
    # Approved stock whose reservation was released again by the Central Team before shipment.
    qty_released: Mapped[int] = mapped_column(nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    decision_notes: Mapped[str | None] = mapped_column(Text)
    replenishment_request_id: Mapped[int | None] = mapped_column(ForeignKey("replenishment_requests.id"),
                                                                 unique=True)
    # "Get this tyre for me": the requester asked the warehouse to find what it cannot supply. On submission the
    # shortfall is handed to the warehouse as a transfer request from another dealer (qty_arranging), so the
    # Central Team only decides the rest of the line.
    find_for_me: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    qty_arranging: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    arranging_transfer_id: Mapped[int | None] = mapped_column(ForeignKey("transfers.id", use_alter=True))


class StockRequestEvent(Base):
    """Append-only history: who (and in which role) did what, with the quantities and status change."""

    __tablename__ = "stock_request_events"
    __table_args__ = (Index("ix_stock_request_events_request", "stock_request_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_request_id: Mapped[int] = mapped_column(ForeignKey("stock_requests.id", ondelete="CASCADE"),
                                                  nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_role: Mapped[str | None] = mapped_column(String(30))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Notification(Base):
    """In-app notification for one user (the bell in the top bar)."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column()
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
