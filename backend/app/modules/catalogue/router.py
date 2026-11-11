import base64
import binascii
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.errors import BusinessRuleError
from app.core.permissions import P
from app.modules.audit.service import record_audit
from app.modules.catalogue import importer, service
from app.modules.catalogue.models import Product
from app.modules.catalogue.schemas import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
    TaxRateIn,
    TaxRateOut,
)
from app.modules.catalogue.template import build_export, build_template
from app.modules.identity.deps import DB, has, require
from app.modules.identity.models import User

router = APIRouter(tags=["catalogue"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _out(user: User, product) -> ProductOut:
    out = ProductOut.model_validate(product)
    if not has(user, P.COST_READ):
        out.cost_price = None
    return out


@router.get("/products", response_model=list[ProductOut])
def list_products(
    db: DB,
    user: Annotated[User, Depends(require(P.CATALOGUE_READ))],
    q: str | None = None,
    brand: str | None = None,
    active: bool | None = None,
    width: int | None = None,
    aspect_ratio: int | None = None,
    rim_diameter: float | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    rows = service.list_products(db, q=q, brand=brand, active=active, width=width, aspect_ratio=aspect_ratio,
                                 rim_diameter=rim_diameter, limit=limit, offset=offset)
    return [_out(user, p) for p in rows]


@router.get("/products/export")
def export_products(db: DB, user: Annotated[User, Depends(require(P.CATALOGUE_IMPORT))]):
    """All products (active and inactive), sorted by SKU, in the import template layout: edit, then import again."""
    products = list(db.execute(select(Product)).scalars())
    record_audit(db, actor_id=user.id, action="product.export", entity_type="product", entity_id=None,
                 summary=f"Exported {len(products)} product(s) to Excel")
    db.commit()
    name = f"TyreGrow_SKUs_{date.today().isoformat()}.xlsx"
    return Response(content=build_export(products), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: DB, user: Annotated[User, Depends(require(P.CATALOGUE_READ))]):
    return _out(user, service.get_product(db, product_id))


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(data: ProductCreate, db: DB, user: Annotated[User, Depends(require(P.CATALOGUE_CREATE))]):
    product = service.create_product(db, user, data)
    db.commit()
    return _out(user, product)


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int, data: ProductUpdate, db: DB, user: Annotated[User, Depends(require(P.CATALOGUE_WRITE))]
):
    product = service.update_product(db, user, product_id, data)
    db.commit()
    return _out(user, product)


@router.get("/tax-rates", response_model=list[TaxRateOut])
def list_tax_rates(db: DB, _: Annotated[User, Depends(require(P.CATALOGUE_READ))]):
    return service.list_tax_rates(db)


@router.post("/tax-rates", response_model=TaxRateOut, status_code=201)
def create_tax_rate(data: TaxRateIn, db: DB, user: Annotated[User, Depends(require(P.PRICING_WRITE))]):
    rate = service.upsert_tax_rate(db, user, data)
    db.commit()
    return rate


@router.put("/tax-rates/{tax_rate_id}", response_model=TaxRateOut)
def update_tax_rate(
    tax_rate_id: int, data: TaxRateIn, db: DB, user: Annotated[User, Depends(require(P.PRICING_WRITE))]
):
    rate = service.upsert_tax_rate(db, user, data, tax_rate_id)
    db.commit()
    return rate


# ---------------------------------------------------------------------------
# Product master import (Excel)
# ---------------------------------------------------------------------------

MAX_IMPORT_BYTES = 5 * 1024 * 1024
Importer = Annotated[User, Depends(require(P.CATALOGUE_IMPORT))]


class ProductImportIn(BaseModel):
    filename: str | None = Field(default=None, max_length=255)
    content_base64: str = Field(min_length=4)
    commit: bool = False   # False = check only (nothing is changed)


@router.get("/products/import/template")
def import_template(_: Importer):
    """The standard blank template every product import uses."""
    return Response(content=build_template(), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="TyreGrow_SKU_Import_Template.xlsx"'})


@router.post("/products/import")
def import_products(data: ProductImportIn, db: DB, user: Importer):
    """Check an Excel product file (commit=false) or import its valid rows (commit=true). Never creates stock."""
    try:
        content = base64.b64decode(data.content_base64.split(",")[-1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BusinessRuleError("The uploaded file could not be decoded.") from exc
    if len(content) > MAX_IMPORT_BYTES:
        raise BusinessRuleError("The file is larger than 5 MB. Split it into smaller files.")
    analysis = importer.analyse(db, content)
    result = None
    if data.commit:
        result = importer.apply(db, user, analysis, data.filename)
        db.commit()
    analysis.pop("_results")
    return {"filename": data.filename, "committed": data.commit, "result": result, **analysis}
