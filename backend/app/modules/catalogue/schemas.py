from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductBase(BaseModel):
    brand: str = Field(min_length=1, max_length=80)
    pattern: str = Field(min_length=1, max_length=120)
    width: int = Field(gt=0, le=500)
    aspect_ratio: int = Field(gt=0, le=100)
    rim_diameter: Decimal = Field(gt=0, le=40, max_digits=4, decimal_places=1)
    construction: str = Field(default="R", min_length=1, max_length=2)
    load_index: str = Field(min_length=1, max_length=10)
    speed_rating: str = Field(min_length=1, max_length=3)
    description: str | None = None
    barcode: str | None = Field(default=None, max_length=50)
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    list_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    rrp: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    is_active: bool = True

    @field_validator("speed_rating", "construction")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("barcode")
    @classmethod
    def _blank_none(cls, v: str | None) -> str | None:
        return v.strip() or None if v else None


class ProductCreate(ProductBase):
    sku: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")

    @field_validator("sku")
    @classmethod
    def _sku_upper(cls, v: str) -> str:
        return v.strip().upper()


class ProductUpdate(BaseModel):
    brand: str | None = Field(default=None, min_length=1, max_length=80)
    pattern: str | None = Field(default=None, min_length=1, max_length=120)
    load_index: str | None = Field(default=None, min_length=1, max_length=10)
    speed_rating: str | None = Field(default=None, min_length=1, max_length=3)
    description: str | None = None
    barcode: str | None = Field(default=None, max_length=50)
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    list_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    rrp: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    is_active: bool | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    brand: str
    pattern: str
    width: int
    aspect_ratio: int
    rim_diameter: Decimal
    construction: str
    load_index: str
    speed_rating: str
    size_display: str
    display_name: str
    description: str | None
    barcode: str | None
    list_price: Decimal | None
    rrp: Decimal | None = None
    cost_price: Decimal | None = None  # populated only for users with catalogue.cost_read
    is_active: bool


class ProductRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    display_name: str
    size_display: str
    brand: str


class TaxRateIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=100)
    rate: Decimal = Field(ge=0, lt=1, max_digits=6, decimal_places=4)
    is_default: bool = False
    is_active: bool = True


class TaxRateOut(TaxRateIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
