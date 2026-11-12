"""Public product configuration: the Brand Pack and Industry Pack values the frontend needs before anyone signs in.

Nothing here is secret: it is what the sign-in page shows. Internal settings never appear.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.industry import PACKS, current_pack, vocab

router = APIRouter(tags=["platform"])


class BrandOut(BaseModel):
    product_name: str
    company_name: str
    support_email: str


class AttributeOut(BaseModel):
    key: str
    label: str
    type: str
    required: bool
    in_spec: bool
    options: list[str]
    unit: str
    help: str
    example: str
    column: bool


class IndustryOut(BaseModel):
    code: str
    name: str
    description: str
    search_example: str
    brand_label: str = "Brand"
    name_label: str = "Name"
    spec_label: str = "Spec"
    tyre_fields: bool = False
    attributes: list[AttributeOut] = []


def _industry(p) -> IndustryOut:
    return IndustryOut(code=p.code, name=p.name, description=p.description, search_example=p.search_example,
                       brand_label=p.brand_label, name_label=p.name_label, spec_label=p.spec_label,
                       tyre_fields=p.tyre_fields,
                       attributes=[AttributeOut(**{**vars(a), "options": list(a.options)}) for a in p.attributes])


class PublicConfigOut(BaseModel):
    brand: BrandOut
    industry: IndustryOut
    terms: dict[str, str]
    currency: str
    timezone: str


@router.get("/config/public", response_model=PublicConfigOut)
def public_config():
    s = get_settings()
    pack = current_pack()
    return PublicConfigOut(
        brand=BrandOut(product_name=s.app_display_name, company_name=s.company_name, support_email=s.support_email),
        industry=_industry(pack),
        terms=vocab.as_dict(), currency=s.default_currency, timezone=s.business_timezone,
    )


@router.get("/config/industry-packs", response_model=list[IndustryOut])
def industry_packs():
    """The Industry Pack library (for set-up screens and sales demos)."""
    return [_industry(p) for p in PACKS.values()]
