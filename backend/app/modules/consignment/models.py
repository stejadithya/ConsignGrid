from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class ConsignmentAllocation(TimestampMixin, Base):
    """Agreed target quantity of a SKU at a reseller location."""

    __tablename__ = "consignment_allocations"
    __table_args__ = (
        UniqueConstraint("location_id", "product_id", name="uq_consignment_allocations_loc_prod"),
        CheckConstraint("target_qty >= 0", name="target_non_negative"),
        CheckConstraint("min_qty IS NULL OR min_qty >= 0", name="min_non_negative"),
        CheckConstraint("max_qty IS NULL OR max_qty >= target_qty", name="max_ge_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    target_qty: Mapped[int] = mapped_column(nullable=False)
    min_qty: Mapped[int | None] = mapped_column()
    max_qty: Mapped[int | None] = mapped_column()
    auto_replenish: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AllocationChange(Base):
    """Audit trail of target changes."""

    __tablename__ = "allocation_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    allocation_id: Mapped[int] = mapped_column(ForeignKey("consignment_allocations.id"), nullable=False, index=True)
    old_target_qty: Mapped[int | None] = mapped_column()
    new_target_qty: Mapped[int] = mapped_column(nullable=False)
    old_auto_replenish: Mapped[bool | None] = mapped_column(Boolean)
    new_auto_replenish: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
