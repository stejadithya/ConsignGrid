from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class Product(TimestampMixin, Base):
    """A tyre SKU. Products are never treated as interchangeable, however similar their size."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("width > 0 AND aspect_ratio > 0 AND rim_diameter > 0", name="positive_dimensions"),
        CheckConstraint("cost_price IS NULL OR cost_price >= 0", name="cost_non_negative"),
        CheckConstraint("list_price IS NULL OR list_price >= 0", name="price_non_negative"),
        CheckConstraint("rrp IS NULL OR rrp >= 0", name="rrp_non_negative"),
        Index("ix_products_size", "width", "aspect_ratio", "rim_diameter"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    brand: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    pattern: Mapped[str] = mapped_column(String(120), nullable=False)
    width: Mapped[int] = mapped_column(nullable=False)
    aspect_ratio: Mapped[int] = mapped_column(nullable=False)
    rim_diameter: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    construction: Mapped[str] = mapped_column(String(2), nullable=False, server_default="R")
    load_index: Mapped[str] = mapped_column(String(10), nullable=False)
    speed_rating: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    barcode: Mapped[str | None] = mapped_column(String(50), unique=True)
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Dealer price: what the reseller is charged (excl. GST & stewardship). Used for consignment sales.
    list_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Recommended retail price to end customers (incl. GST, excl. stewardship). Reference only.
    rrp: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))

    @property
    def size_display(self) -> str:
        rim = self.rim_diameter
        rim_str = str(int(rim)) if rim == int(rim) else str(rim)
        return f"{self.width}/{self.aspect_ratio}{self.construction}{rim_str}"

    @property
    def display_name(self) -> str:
        return f"{self.brand} {self.pattern} {self.size_display} {self.load_index}{self.speed_rating}"

    @property
    def tyre_label(self) -> str:
        """How people identify a tyre in messages: model and size first, SKU in brackets."""
        return f"{self.display_name} ({self.sku})"


class TaxRate(TimestampMixin, Base):
    """Configurable tax rates. No jurisdiction's rate is hard-coded (A-007)."""

    __tablename__ = "tax_rates"
    __table_args__ = (
        CheckConstraint("rate >= 0 AND rate < 1", name="rate_fraction"),
        Index("uq_tax_rates_single_default", "is_default", unique=True, postgresql_where=text("is_default")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)  # 0.1000 = 10%
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
