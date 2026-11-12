from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin
from app.core.industry import current_pack


class Product(TimestampMixin, Base):
    """A stocked item (SKU). Products are never treated as interchangeable, however similar they are.

    The tyres Industry Pack uses the tyre columns (width … speed_rating); every other pack stores its own attributes
    in `attributes` (see app/core/industry.py and catalogue/attributes.py). `brand` and `pattern` (the model or
    product name) are common to every pack."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("(width IS NULL OR width > 0) AND (aspect_ratio IS NULL OR aspect_ratio > 0) "
                        "AND (rim_diameter IS NULL OR rim_diameter > 0)", name="positive_dimensions"),
        CheckConstraint("(width IS NULL) = (aspect_ratio IS NULL) AND (width IS NULL) = (rim_diameter IS NULL)",
                        name="tyre_size_complete"),
        CheckConstraint("cost_price IS NULL OR cost_price >= 0", name="cost_non_negative"),
        CheckConstraint("list_price IS NULL OR list_price >= 0", name="price_non_negative"),
        CheckConstraint("rrp IS NULL OR rrp >= 0", name="rrp_non_negative"),
        Index("ix_products_size", "width", "aspect_ratio", "rim_diameter"),
        Index("ix_products_attributes", "attributes", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    brand: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    pattern: Mapped[str] = mapped_column(String(120), nullable=False)
    width: Mapped[int | None] = mapped_column()
    aspect_ratio: Mapped[int | None] = mapped_column()
    rim_diameter: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    construction: Mapped[str] = mapped_column(String(2), nullable=False, server_default="R")
    load_index: Mapped[str | None] = mapped_column(String(10))
    speed_rating: Mapped[str | None] = mapped_column(String(3))
    # Industry Pack attributes (non-tyre packs), e.g. {"ref": "71933215", "size": "4.5 x 30 mm", "sterile": true}.
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict,
                                                       server_default=text("'{}'::jsonb"))
    description: Mapped[str | None] = mapped_column(Text)
    barcode: Mapped[str | None] = mapped_column(String(50), unique=True)
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Dealer price: what the reseller is charged (excl. GST & stewardship). Used for consignment sales.
    list_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Recommended retail price to end customers (incl. GST, excl. stewardship). Reference only.
    rrp: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))

    @property
    def has_tyre_size(self) -> bool:
        return self.width is not None and self.aspect_ratio is not None and self.rim_diameter is not None

    @property
    def size_display(self) -> str:
        """The short specification: the tyre size (205/55R16), or the pack's in-spec attributes."""
        if self.has_tyre_size:
            rim = self.rim_diameter
            rim_str = str(int(rim)) if rim == int(rim) else str(rim)
            return f"{self.width}/{self.aspect_ratio}{self.construction}{rim_str}"
        from app.modules.catalogue.attributes import spec_text

        return spec_text(current_pack(), self.attributes)

    @property
    def size_full(self) -> str:
        """Specification with the load index and speed rating for tyres ("205/55R16 91H")."""
        tail = f"{self.load_index or ''}{self.speed_rating or ''}"
        return f"{self.size_display} {tail}".strip()

    @property
    def display_name(self) -> str:
        if self.has_tyre_size:
            return f"{self.brand} {self.pattern} {self.size_display} {self.load_index}{self.speed_rating}"
        return " ".join(p for p in (self.brand, self.pattern, self.size_display) if p)

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
