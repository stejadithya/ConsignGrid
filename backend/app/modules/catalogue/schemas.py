from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.industry import current_pack
from app.modules.catalogue.attributes import AttributeError_, clean_attributes

TYRE_REQUIRED = (("width", "Width"), ("aspect_ratio", "Aspect ratio"), ("rim_diameter", "Rim diameter"),
                 ("load_index", "Load index"), ("speed_rating", "Speed rating"))
TYRE_ONLY = ("width", "aspect_ratio", "rim_diameter", "load_index", "speed_rating")


class ProductBase(BaseModel):
    brand: str = Field(min_length=1, max_length=80)
    pattern: str = Field(min_length=1, max_length=120)
    # Tyre columns: required by the tyres Industry Pack, not used by the others (see _check_pack).
    width: int | None = Field(default=None, gt=0, le=500)
    aspect_ratio: int | None = Field(default=None, gt=0, le=100)
    rim_diameter: Decimal | None = Field(default=None, gt=0, le=40, max_digits=4, decimal_places=1)
    construction: str = Field(default="R", min_length=1, max_length=2)
    load_index: str | None = Field(default=None, min_length=1, max_length=10)
    speed_rating: str | None = Field(default=None, min_length=1, max_length=3)
    # Industry Pack attributes (non-tyre packs), validated and converted against the pack.
    attributes: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    barcode: str | None = Field(default=None, max_length=50)
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    list_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    rrp: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    is_active: bool = True

    @field_validator("speed_rating", "construction")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.strip().upper() if v is not None else None

    @model_validator(mode="after")
    def _check_pack(self):
        pack = current_pack()
        if pack.tyre_fields:
            missing = [label for key, label in TYRE_REQUIRED if getattr(self, key) is None]
            if missing:
                raise ValueError(f"Required for a tyre: {', '.join(missing)}")
            if self.attributes:
                raise ValueError("Tyres use the size fields, not attributes")
            return self
        given = [key for key in TYRE_ONLY if getattr(self, key) is not None]
        if given:
            raise ValueError(f"Not used by the {pack.name} pack: {', '.join(given)}")
        try:
            self.attributes = clean_attributes(pack, self.attributes)
        except AttributeError_ as exc:
            raise ValueError(str(exc)) from exc
        return self

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
    # Replaces the whole set of attributes (non-tyre packs); validated against the pack.
    attributes: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _check_attributes(self):
        if self.attributes is None:
            return self
        pack = current_pack()
        if pack.tyre_fields:
            raise ValueError("Tyres use the size fields, not attributes")
        try:
            self.attributes = clean_attributes(pack, self.attributes)
        except AttributeError_ as exc:
            raise ValueError(str(exc)) from exc
        return self


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    brand: str
    pattern: str
    width: int | None
    aspect_ratio: int | None
    rim_diameter: Decimal | None
    construction: str
    load_index: str | None
    speed_rating: str | None
    attributes: dict[str, Any] = Field(default_factory=dict)
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
