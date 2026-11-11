from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class InvoiceDocStatus(StrEnum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    VOID = "VOID"


class Invoice(Base):
    """Invoice for confirmed consignment sales. Financial values are snapshots, never recalculated."""

    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    reseller_id: Mapped[int] = mapped_column(ForeignKey("resellers.id"), nullable=False, index=True)
    status: Mapped[InvoiceDocStatus] = mapped_column(
        Enum(InvoiceDocStatus, name="invoice_status", native_enum=False, length=10),
        nullable=False, default=InvoiceDocStatus.DRAFT, index=True,
    )
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    bill_to_name: Mapped[str] = mapped_column(String(200), nullable=False)
    bill_to_account_ref: Mapped[str] = mapped_column(String(30), nullable=False)
    bill_to_address: Mapped[str | None] = mapped_column(Text)
    bill_to_tax_number: Mapped[str | None] = mapped_column(String(50))
    external_reference: Mapped[str | None] = mapped_column(String(100))   # the Xero invoice number (release 1.11)
    xero_recorded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    xero_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    issued_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(Text)

    lines: Mapped[list["InvoiceLine"]] = relationship(order_by="InvoiceLine.id")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (
        # A sale line can be on at most one non-void invoice: duplicate invoicing is impossible.
        Index("uq_invoice_lines_active_sale_line", "sale_line_id", unique=True, postgresql_where=text("is_active")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    sale_line_id: Mapped[int] = mapped_column(ForeignKey("consignment_sale_lines.id"), nullable=False, index=True)
    sale_number: Mapped[str] = mapped_column(String(20), nullable=False)
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    location_code: Mapped[str] = mapped_column(String(30), nullable=False)
    sku: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_code: Mapped[str] = mapped_column(String(20), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    line_net: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
