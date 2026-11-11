from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator

from app.modules.customers.models import LocationType, ResellerStatus, TransferConsent


class AgreementIn(BaseModel):
    reference: str = Field(min_length=1, max_length=50)
    start_date: date | None = None
    end_date: date | None = None
    transfer_consent: TransferConsent = TransferConsent.PER_TRANSFER
    auto_replenish_default: bool = True
    notes: str | None = None


class AgreementOut(AgreementIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class LocationIn(BaseModel):
    code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=200)
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    postcode: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=100)
    contact_phone: str | None = Field(default=None, max_length=50)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.strip().upper() if v else v


Required = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DealerShopIn(LocationIn):
    """A dealer shop (delivery location): name, address line 1 and city are required (finding 9).
    The code is optional: left out, it becomes {ACCOUNT_REF}-01, -02 … (finding 11)."""

    code: str | None = Field(default=None, min_length=1, max_length=30, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    address_line1: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    city: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class WarehouseIn(LocationIn):
    is_default_warehouse: bool = False


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    type: LocationType
    reseller_id: int | None
    reseller_name: str | None = None      # the dealer's business name (consignment shops)
    is_default_warehouse: bool
    address_line1: str | None
    address_line2: str | None
    city: str | None
    region: str | None
    postcode: str | None
    country: str | None
    contact_phone: str | None
    is_active: bool


class LocationRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    type: LocationType
    reseller_id: int | None


class ResellerBase(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    trading_name: str | None = Field(default=None, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    billing_address: str | None = None
    tax_number: str | None = Field(default=None, max_length=50)
    sales_rep_user_id: int | None = None
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    tax_rate_id: int | None = None
    notes: str | None = None


class ResellerCreate(ResellerBase):
    # New dealer (False: stock comes through stock requests) or existing (True: holds the supplier's stock already).
    joined_with_stock: bool | None = None
    # Omitted → generated from the business name and the first shop's city (D4).
    account_ref: str | None = Field(default=None, min_length=1, max_length=30, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    business_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    # Mandatory for every new dealer (finding 9).
    contact_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    email: EmailStr
    phone: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    billing_address: Required
    sales_rep_user_id: int
    agreement: AgreementIn | None = None
    locations: list[DealerShopIn] = Field(min_length=1)
    # Also create the dealer's login (email = dealer email). The form ticks this by default (D7).
    create_login: bool = False

    @field_validator("account_ref")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.strip().upper() if v else None


class AccountRefPreview(BaseModel):
    account_ref: str
    hint: str = "Final reference is confirmed when you save"


MANDATORY_DEALER_FIELDS = ("business_name", "contact_name", "email", "phone", "billing_address", "sales_rep_user_id")


class ResellerUpdate(BaseModel):
    business_name: str | None = Field(default=None, min_length=1, max_length=200)
    trading_name: str | None = Field(default=None, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    billing_address: str | None = None
    tax_number: str | None = Field(default=None, max_length=50)
    sales_rep_user_id: int | None = None
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    tax_rate_id: int | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _no_blanking(self) -> "ResellerUpdate":
        blanked = [k for k in MANDATORY_DEALER_FIELDS if k in self.model_fields_set
                   and (getattr(self, k) is None or (isinstance(getattr(self, k), str) and not getattr(self, k).strip()))]
        if blanked:
            raise ValueError(f"These details are required and cannot be removed: {', '.join(blanked)}")
        return self


class ResellerStatusChange(BaseModel):
    status: ResellerStatus
    reason: str = Field(min_length=3, max_length=500)


class ResellerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_ref: str
    business_name: str
    trading_name: str | None
    status: ResellerStatus
    sales_rep_user_id: int | None
    sales_rep_name: str | None = None
    location_count: int = 0


class DealerLoginOut(BaseModel):
    """Returned once, when the login is created with the dealer. Never stored in plain text, never emailed."""

    email: str
    temporary_password: str


class ResellerOut(ResellerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_ref: str
    status: ResellerStatus
    joined_with_stock: bool | None = None
    sales_rep_name: str | None = None
    agreement: AgreementOut | None
    locations: list[LocationOut]
    login: DealerLoginOut | None = None


class CustomerPriceIn(BaseModel):
    product_id: int
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    valid_from: date
    valid_to: date | None = None


class CustomerPriceOut(CustomerPriceIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reseller_id: int
    sku: str | None = None
