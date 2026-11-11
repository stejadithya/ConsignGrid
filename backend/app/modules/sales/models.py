from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class SaleSource(StrEnum):
    RESELLER_REPORT = "RESELLER_REPORT"
    STOCKTAKE = "STOCKTAKE"
    REP_VISIT = "REP_VISIT"
    OTHER = "OTHER"
    CASH_SALE = "CASH_SALE"   # walk-in customer paying at the warehouse; stock leaves the warehouse


class InvoiceStatus(StrEnum):
    UNINVOICED = "UNINVOICED"
    DRAFTED = "DRAFTED"          # on a draft invoice (not yet finalised)
    INVOICED = "INVOICED"        # on an issued invoice
    NOT_CHARGEABLE = "NOT_CHARGEABLE"  # fully reversed


class ConsignmentSale(Base):
    __tablename__ = "consignment_sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    reseller_id: Mapped[int] = mapped_column(ForeignKey("resellers.id"), nullable=False, index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[SaleSource] = mapped_column(Enum(SaleSource, name="sale_source", native_enum=False, length=20),
                                               nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(100))
    stocktake_id: Mapped[int | None] = mapped_column(ForeignKey("stocktakes.id", use_alter=True))
    recorded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    inventory_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_transactions.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    # Cash sales only: who bought (free text, optional).
    customer_name: Mapped[str | None] = mapped_column(String(200))
    customer_phone: Mapped[str | None] = mapped_column(String(50))

    lines: Mapped[list["ConsignmentSaleLine"]] = relationship(back_populates="sale", order_by="ConsignmentSaleLine.id")


class ConsignmentSaleLine(Base):
    __tablename__ = "consignment_sale_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("reversed_qty >= 0 AND reversed_qty <= quantity", name="reversed_range"),
        CheckConstraint("unit_price >= 0", name="price_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("consignment_sales.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(nullable=False)
    reversed_qty: Mapped[int] = mapped_column(nullable=False, default=0)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_source: Mapped[str] = mapped_column(String(20), nullable=False)
    price_override_reason: Mapped[str | None] = mapped_column(Text)
    tax_rate_id: Mapped[int | None] = mapped_column(ForeignKey("tax_rates.id"))
    tax_code: Mapped[str] = mapped_column(String(20), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    invoice_status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="sale_invoice_status", native_enum=False, length=20),
        nullable=False, default=InvoiceStatus.UNINVOICED, index=True,
    )

    sale: Mapped[ConsignmentSale] = relationship(back_populates="lines")

    @property
    def chargeable_qty(self) -> int:
        return self.quantity - self.reversed_qty
