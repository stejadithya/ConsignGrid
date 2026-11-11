from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Bucket(StrEnum):
    ON_HAND = "ON_HAND"
    RESERVED = "RESERVED"
    BLOCKED = "BLOCKED"


class TxnType(StrEnum):
    OPENING_BALANCE = "OPENING_BALANCE"
    SUPPLIER_RECEIPT = "SUPPLIER_RECEIPT"
    ADJUSTMENT = "ADJUSTMENT"
    BLOCK = "BLOCK"
    UNBLOCK = "UNBLOCK"
    WRITE_OFF = "WRITE_OFF"
    RESERVATION = "RESERVATION"
    RESERVATION_RELEASE = "RESERVATION_RELEASE"
    REPLENISHMENT_DISPATCH = "REPLENISHMENT_DISPATCH"
    REPLENISHMENT_RECEIPT = "REPLENISHMENT_RECEIPT"
    TRANSFER_COLLECTION = "TRANSFER_COLLECTION"
    TRANSFER_RECEIPT = "TRANSFER_RECEIPT"
    TRANSIT_RESOLUTION = "TRANSIT_RESOLUTION"
    CONSIGNMENT_SALE = "CONSIGNMENT_SALE"
    SALE_REVERSAL = "SALE_REVERSAL"
    STOCKTAKE_ADJUSTMENT = "STOCKTAKE_ADJUSTMENT"
    # A dealer's initial stock was entered wrongly: the correction points at the entry it corrects.
    INITIAL_STOCK_CORRECTION = "INITIAL_STOCK_CORRECTION"


class ReservationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    RELEASED = "RELEASED"
    CLOSED = "CLOSED"  # partly consumed, remainder released


class ReservationPurpose(StrEnum):
    REPLENISHMENT = "REPLENISHMENT"
    TRANSFER = "TRANSFER"


class InventoryTransaction(Base):
    """Header of an append-only group of ledger entries. Never updated or deleted."""

    __tablename__ = "inventory_transactions"
    __table_args__ = (Index("ix_inventory_transactions_reference", "reference_type", "reference_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    txn_type: Mapped[TxnType] = mapped_column(
        Enum(TxnType, name="txn_type", native_enum=False, length=30), nullable=False, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reference_type: Mapped[str | None] = mapped_column(String(40))
    reference_id: Mapped[int | None] = mapped_column()
    reference_number: Mapped[str | None] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    reverses_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_transactions.id"))

    entries: Mapped[list["InventoryEntry"]] = relationship(back_populates="transaction", order_by="InventoryEntry.id")


class InventoryEntry(Base):
    """Signed quantity delta for one (product, location, bucket). Append-only."""

    __tablename__ = "inventory_entries"
    __table_args__ = (
        CheckConstraint("quantity <> 0", name="non_zero"),
        Index("ix_inventory_entries_loc_prod", "location_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("inventory_transactions.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    bucket: Mapped[Bucket] = mapped_column(Enum(Bucket, name="bucket", native_enum=False, length=10), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("stock_reservations.id"), index=True)

    transaction: Mapped[InventoryTransaction] = relationship(back_populates="entries")


class StockBalance(Base):
    """Projection of the ledger for physical locations. Constraints forbid negative availability."""

    __tablename__ = "stock_balances"
    __table_args__ = (
        CheckConstraint("on_hand >= 0", name="on_hand_non_negative"),
        CheckConstraint("reserved >= 0", name="reserved_non_negative"),
        CheckConstraint("blocked >= 0", name="blocked_non_negative"),
        CheckConstraint("reserved + blocked <= on_hand", name="available_non_negative"),
        Index("ix_stock_balances_product", "product_id"),
    )

    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    on_hand: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    reserved: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    blocked: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved - self.blocked


class StockReservation(Base):
    __tablename__ = "stock_reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive"),
        CheckConstraint("consumed_qty >= 0 AND released_qty >= 0", name="non_negative"),
        CheckConstraint("consumed_qty + released_qty <= quantity", name="not_over_used"),
        Index("ix_stock_reservations_reference", "reference_type", "reference_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    consumed_qty: Mapped[int] = mapped_column(nullable=False, default=0)
    released_qty: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus, name="reservation_status", native_enum=False, length=10),
        nullable=False, default=ReservationStatus.ACTIVE,
    )
    purpose: Mapped[ReservationPurpose] = mapped_column(
        Enum(ReservationPurpose, name="reservation_purpose", native_enum=False, length=20), nullable=False
    )
    reference_type: Mapped[str | None] = mapped_column(String(40))
    reference_id: Mapped[int | None] = mapped_column()
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    @property
    def open_qty(self) -> int:
        return self.quantity - self.consumed_qty - self.released_qty
