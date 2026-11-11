from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin


class ResellerStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ON_HOLD = "ON_HOLD"
    CLOSED = "CLOSED"


class TransferConsent(StrEnum):
    PRE_AUTHORISED = "PRE_AUTHORISED"
    PER_TRANSFER = "PER_TRANSFER"
    NOT_ALLOWED = "NOT_ALLOWED"


class LocationType(StrEnum):
    WAREHOUSE = "WAREHOUSE"
    CONSIGNMENT = "CONSIGNMENT"
    TRANSIT = "TRANSIT"
    SUPPLIER = "SUPPLIER"
    SOLD = "SOLD"
    ADJUSTMENT = "ADJUSTMENT"
    OPENING = "OPENING"
    SCRAP = "SCRAP"


PHYSICAL_LOCATION_TYPES = frozenset({LocationType.WAREHOUSE, LocationType.CONSIGNMENT, LocationType.TRANSIT})

# System (transit/virtual) locations created by migration 0001: (type, code, name).
SYSTEM_LOCATIONS = [
    (LocationType.TRANSIT, "SYS-TRANSIT", "In transit"),
    (LocationType.SUPPLIER, "SYS-SUPPLIER", "Suppliers"),
    (LocationType.SOLD, "SYS-SOLD", "Sold to end customers"),
    (LocationType.ADJUSTMENT, "SYS-ADJUSTMENT", "Inventory adjustments"),
    (LocationType.OPENING, "SYS-OPENING", "Opening balances"),
    (LocationType.SCRAP, "SYS-SCRAP", "Scrapped / written off"),
]
SYSTEM_LOCATION_CODES = {t: code for t, code, _ in SYSTEM_LOCATIONS}


class Reseller(TimestampMixin, Base):
    __tablename__ = "resellers"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_ref: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    business_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    trading_name: Mapped[str | None] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    billing_address: Mapped[str | None] = mapped_column(Text)
    tax_number: Mapped[str | None] = mapped_column(String(50))
    sales_rep_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", use_alter=True), index=True)
    payment_terms_days: Mapped[int | None] = mapped_column()
    tax_rate_id: Mapped[int | None] = mapped_column(ForeignKey("tax_rates.id"))  # override of default
    status: Mapped[ResellerStatus] = mapped_column(
        Enum(ResellerStatus, name="reseller_status", native_enum=False, length=20),
        nullable=False, default=ResellerStatus.ACTIVE,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    # The single system account that groups walk-in cash sales from the warehouse; hidden from reseller lists.
    is_cash_account: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # How the dealer joined (UAT round 2): True = already held the supplier's stock (recorded as initial stock);
    # False = new dealer, whose stock comes through stock requests and the warehouse. None = added before this.
    joined_with_stock: Mapped[bool | None] = mapped_column(Boolean)

    locations: Mapped[list["Location"]] = relationship(back_populates="reseller", order_by="Location.id")
    agreement: Mapped["ConsignmentAgreement | None"] = relationship(back_populates="reseller", uselist=False)


class ConsignmentAgreement(TimestampMixin, Base):
    __tablename__ = "consignment_agreements"

    id: Mapped[int] = mapped_column(primary_key=True)
    reseller_id: Mapped[int] = mapped_column(ForeignKey("resellers.id"), unique=True, nullable=False)
    reference: Mapped[str] = mapped_column(String(50), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    transfer_consent: Mapped[TransferConsent] = mapped_column(
        Enum(TransferConsent, name="transfer_consent", native_enum=False, length=20),
        nullable=False, default=TransferConsent.PER_TRANSFER,
    )
    auto_replenish_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    reseller: Mapped[Reseller] = relationship(back_populates="agreement")


class ConsignmentAgreementFile(Base):
    """A copy of the signed consignment agreement (finding 14, D8): PDF or photo, at most 5 MB. Deleting hides it."""

    __tablename__ = "consignment_agreement_files"
    __table_args__ = (
        CheckConstraint("size_bytes > 0 AND size_bytes <= 5242880", name="agreement_file_size"),
        CheckConstraint("content_type IN ('application/pdf', 'image/jpeg', 'image/png', 'image/webp')",
                        name="agreement_file_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reseller_id: Mapped[int] = mapped_column(ForeignKey("resellers.id"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(30), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class Location(TimestampMixin, Base):
    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint(
            "(type = 'CONSIGNMENT') = (reseller_id IS NOT NULL)", name="consignment_has_reseller"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[LocationType] = mapped_column(
        Enum(LocationType, name="location_type", native_enum=False, length=20), nullable=False, index=True
    )
    reseller_id: Mapped[int | None] = mapped_column(ForeignKey("resellers.id"), index=True)
    is_default_warehouse: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    postcode: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(100))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    reseller: Mapped[Reseller | None] = relationship(back_populates="locations")

    @property
    def reseller_name(self) -> str | None:
        """The dealer's business name: how people identify a shop (UAT round 2)."""
        return self.reseller.business_name if self.reseller else None

    @property
    def is_physical(self) -> bool:
        return self.type in PHYSICAL_LOCATION_TYPES


class CustomerPrice(TimestampMixin, Base):
    """Reseller-specific agreed price for a product, effective from a date."""

    __tablename__ = "customer_prices"
    __table_args__ = (
        UniqueConstraint("reseller_id", "product_id", "valid_from", name="uq_customer_prices_effective"),
        CheckConstraint("unit_price >= 0", name="price_non_negative"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reseller_id: Mapped[int] = mapped_column(ForeignKey("resellers.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
