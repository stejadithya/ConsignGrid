from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.replenishment.models import Priority


class TransferStatus(StrEnum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"            # source selected and stock reserved at source
    IN_TRANSIT = "IN_TRANSIT"        # collected from source
    RECEIVED_WITH_DISCREPANCY = "RECEIVED_WITH_DISCREPANCY"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


OPEN_TRANSFER_STATUSES = (TransferStatus.REQUESTED, TransferStatus.APPROVED, TransferStatus.IN_TRANSIT,
                          TransferStatus.RECEIVED_WITH_DISCREPANCY)


class Transfer(Base):
    """Dealership-controlled movement of unsold consignment stock between resellers. Never a sale."""

    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("source_location_id IS NULL OR source_location_id <> destination_location_id",
                        name="distinct_locations"),
        CheckConstraint("qty_collected >= 0 AND qty_received >= 0 AND qty_returned >= 0 AND qty_lost >= 0",
                        name="non_negative"),
        CheckConstraint("qty_collected <= quantity", name="collected_within_quantity"),
        CheckConstraint("qty_received + qty_returned + qty_lost <= qty_collected", name="resolved_within_collected"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(nullable=False)
    destination_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    destination_reseller_id: Mapped[int] = mapped_column(ForeignKey("resellers.id"), nullable=False, index=True)
    source_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), index=True)
    source_reseller_id: Mapped[int | None] = mapped_column(ForeignKey("resellers.id"), index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    urgency: Mapped[Priority] = mapped_column(
        Enum(Priority, name="transfer_urgency", native_enum=False, length=10), nullable=False, default=Priority.HIGH
    )
    status: Mapped[TransferStatus] = mapped_column(
        Enum(TransferStatus, name="transfer_status", native_enum=False, length=30),
        nullable=False, default=TransferStatus.REQUESTED, index=True,
    )
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_notes: Mapped[str | None] = mapped_column(Text)
    source_consent_reference: Mapped[str | None] = mapped_column(String(200))
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("stock_reservations.id"))
    collected_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    qty_collected: Mapped[int] = mapped_column(nullable=False, default=0)
    received_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_by_name: Mapped[str | None] = mapped_column(String(120))   # the person at the dealer who took it
    receipt_notes: Mapped[str | None] = mapped_column(Text)
    qty_received: Mapped[int] = mapped_column(nullable=False, default=0)
    qty_returned: Mapped[int] = mapped_column(nullable=False, default=0)
    qty_lost: Mapped[int] = mapped_column(nullable=False, default=0)
    destination_request_id: Mapped[int | None] = mapped_column(ForeignKey("replenishment_requests.id"))
    source_request_id: Mapped[int | None] = mapped_column(ForeignKey("replenishment_requests.id"))
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    # How the tyres travel (release 1.11, finding 23): a sales rep collects and delivers, or a courier.
    shipping_method: Mapped[str | None] = mapped_column(String(20))   # COURIER / SALES_REP; null = not arranged
    carrier_reference: Mapped[str | None] = mapped_column(String(100))
    tracking_number: Mapped[str | None] = mapped_column(String(100))
    carried_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    shipping_arranged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipping_arranged_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    collected_from_name: Mapped[str | None] = mapped_column(String(120))   # who handed the tyres over at the source
    note_emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note_email_to: Mapped[str | None] = mapped_column(String(255))
    note_email_error: Mapped[str | None] = mapped_column(Text)
    # Route (UAT round 2): DIRECT (source dealer → destination dealer) or VIA_WAREHOUSE (source → warehouse, where
    # the tyres are received and checked → destination). Null = direct. The stock stays in transit throughout.
    route: Mapped[str | None] = mapped_column(String(20))
    warehouse_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    warehouse_received_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    warehouse_check_notes: Mapped[str | None] = mapped_column(Text)

    @property
    def qty_in_transit(self) -> int:
        return self.qty_collected - self.qty_received - self.qty_returned - self.qty_lost
