from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin


class POStatus(StrEnum):
    OPEN = "OPEN"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


class PurchaseOrder(TimestampMixin, Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(200), nullable=False)
    supplier_reference: Mapped[str | None] = mapped_column(String(100))
    warehouse_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    expected_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[POStatus] = mapped_column(
        Enum(POStatus, name="po_status", native_enum=False, length=20), nullable=False, default=POStatus.OPEN
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        back_populates="purchase_order", order_by="PurchaseOrderLine.id", cascade="all, delete-orphan"
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        CheckConstraint("qty_ordered > 0", name="ordered_positive"),
        CheckConstraint("qty_received >= 0 AND qty_received <= qty_ordered", name="received_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    qty_ordered: Mapped[int] = mapped_column(nullable=False)
    qty_received: Mapped[int] = mapped_column(nullable=False, default=0)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines")

    @property
    def qty_outstanding(self) -> int:
        return self.qty_ordered - self.qty_received


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    warehouse_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    supplier_reference: Mapped[str | None] = mapped_column(String(100))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    received_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    inventory_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_transactions.id"))
    notes: Mapped[str | None] = mapped_column(Text)

    lines: Mapped[list["GoodsReceiptLine"]] = relationship(order_by="GoodsReceiptLine.id")


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_lines"
    __table_args__ = (
        CheckConstraint("qty_received > 0", name="received_positive"),
        CheckConstraint("qty_damaged >= 0 AND qty_damaged <= qty_received", name="damaged_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    goods_receipt_id: Mapped[int] = mapped_column(ForeignKey("goods_receipts.id"), nullable=False, index=True)
    purchase_order_line_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_order_lines.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    qty_received: Mapped[int] = mapped_column(nullable=False)
    qty_damaged: Mapped[int] = mapped_column(nullable=False, default=0)
