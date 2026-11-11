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


class IndustryOut(BaseModel):
    code: str
    name: str
    description: str
    search_example: str


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
        industry=IndustryOut(code=pack.code, name=pack.name, description=pack.description,
                             search_example=pack.search_example),
        terms=vocab.as_dict(), currency=s.default_currency, timezone=s.business_timezone,
    )


@router.get("/config/industry-packs", response_model=list[IndustryOut])
def industry_packs():
    """The Industry Pack library (for set-up screens and sales demos)."""
    return [IndustryOut(code=p.code, name=p.name, description=p.description, search_example=p.search_example)
            for p in PACKS.values()]
