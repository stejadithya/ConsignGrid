from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class StocktakeStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"                  # legacy: counted before P-018, approved by staff
    AWAITING_RESELLER = "AWAITING_RESELLER"  # shortages found; the reseller confirms each as sold or missing
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"
    # Release 1.11 (finding 29): the find window. These pause the automatic invoicing.
    RECHECK_REQUESTED = "RECHECK_REQUESTED"  # the dealer found the tyres and asked for a re-check
    DISPUTED = "DISPUTED"                    # the dealer disagrees with the count; WM/RM follow up
    SUPERSEDED = "SUPERSEDED"                # replaced by a re-count (see recount_of_id on the new check)


class Stocktake(Base):
    __tablename__ = "stocktakes"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    reseller_id: Mapped[int] = mapped_column(ForeignKey("resellers.id"), nullable=False, index=True)
    count_date: Mapped[date] = mapped_column(Date, nullable=False)
    counted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[StocktakeStatus] = mapped_column(
        Enum(StocktakeStatus, name="stocktake_status", native_enum=False, length=20),
        nullable=False, default=StocktakeStatus.DRAFT, index=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("consignment_sales.id"))
    # Reseller confirmation of shortages (P-018).
    confirm_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    confirmed_on_behalf_reason: Mapped[str | None] = mapped_column(Text)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    recheck_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recheck_requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    recheck_note: Mapped[str | None] = mapped_column(Text)
    disputed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disputed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    dispute_note: Mapped[str | None] = mapped_column(Text)
    recount_of_id: Mapped[int | None] = mapped_column(ForeignKey("stocktakes.id"))   # this check re-counts that one
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    lines: Mapped[list["StocktakeLine"]] = relationship(order_by="StocktakeLine.id", cascade="all, delete-orphan")


class StocktakeLine(Base):
    __tablename__ = "stocktake_lines"
    __table_args__ = (
        UniqueConstraint("stocktake_id", "product_id", name="uq_stocktake_lines_product"),
        CheckConstraint("counted_qty >= 0", name="counted_non_negative"),
        CheckConstraint("counted_damaged_qty >= 0 AND counted_damaged_qty <= counted_qty", name="damaged_range"),
        CheckConstraint("qty_sold >= 0 AND qty_missing >= 0", name="classification_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stocktake_id: Mapped[int] = mapped_column(ForeignKey("stocktakes.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    expected_qty: Mapped[int | None] = mapped_column()  # snapshot of on-hand when submitted
    expected_blocked_qty: Mapped[int | None] = mapped_column()
    counted_qty: Mapped[int] = mapped_column(nullable=False)
    counted_damaged_qty: Mapped[int] = mapped_column(nullable=False, default=0)
    qty_sold: Mapped[int] = mapped_column(nullable=False, default=0)
    qty_missing: Mapped[int] = mapped_column(nullable=False, default=0)
    # Shortage stock blocked while the reseller has not confirmed it as sold or missing.
    qty_held: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text)

    @property
    def variance(self) -> int | None:
        return None if self.expected_qty is None else self.counted_qty - self.expected_qty

    @property
    def shortage(self) -> int:
        v = self.variance
        return 0 if v is None or v >= 0 else -v


class StockCheckSchedule(Base):
    """When a dealer shop's next stock check is due, if someone moved it, and what reminders went out (UAT round 2).

    Without a row (or with next_check_on empty) a shop is due STOCK_CHECK_EVERY_DAYS (30) after its last count.
    """

    __tablename__ = "stock_check_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), unique=True, nullable=False)
    next_check_on: Mapped[date | None] = mapped_column(Date)          # moved to this date (cleared by the next count)
    moved_reason: Mapped[str | None] = mapped_column(Text)
    moved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    moved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_notified_on: Mapped[date | None] = mapped_column(Date)       # "due today" reminder to the rep
    overdue_notified_on: Mapped[date | None] = mapped_column(Date)   # last "overdue" alert to the WM and RM
