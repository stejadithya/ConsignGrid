import re

from sqlalchemy import String, cast, func, literal_column, or_, select, update
from sqlalchemy.orm import Session

from app.core.db import flush_or_conflict
from app.core.errors import NotFoundError
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product, TaxRate
from app.modules.catalogue.schemas import ProductCreate, ProductUpdate, TaxRateIn
from app.modules.identity.models import User


def get_product(db: Session, product_id: int) -> Product:
    p = db.get(Product, product_id)
    if p is None:
        raise NotFoundError("Product not found")
    return p


def search_tokens(query: str) -> list[str]:
    """The words of a search, lower case, without punctuation ("195/65 R15" → ["195", "65", "r15"])."""
    return [t for t in (re.sub(r"[^0-9a-z]", "", w) for w in re.split(r"[\s/\\\-_.,;:+|]+", query.lower())) if t]


def _compact(expr):
    return func.regexp_replace(func.lower(expr), "[^a-z0-9]", "", "g")


def _search_fields():
    rim = func.regexp_replace(cast(Product.rim_diameter, String), r"\.0+$", "")
    size = func.concat(cast(Product.width, String), cast(Product.aspect_ratio, String), Product.construction, rim,
                       " ", Product.load_index, Product.speed_rating)
    # Attribute values only (not their keys): ["71933215", "4.5 x 30 mm"] for a medical device.
    attrs = cast(func.jsonb_path_query_array(Product.attributes, literal_column("'$.*'::jsonpath")), String)
    return (Product.sku, Product.brand, Product.pattern, func.coalesce(Product.barcode, ""),
            func.coalesce(Product.description, ""), size, attrs)


def list_products(
    db: Session, *, q: str | None = None, brand: str | None = None, active: bool | None = None,
    width: int | None = None, aspect_ratio: int | None = None, rim_diameter: float | None = None,
    limit: int = 200, offset: int = 0,
) -> list[Product]:
    stmt = select(Product)
    for token in search_tokens(q or ""):
        # Every word must appear in one field. Case, spaces and punctuation are ignored, and the tyre size counts, so
        # "195 65", "19565" and "195/65" all find 195/65R15 (the same rule as the app's search boxes).
        like = f"%{token}%"
        stmt = stmt.where(or_(*(_compact(f).like(like) for f in _search_fields())))
    if brand:
        stmt = stmt.where(Product.brand.ilike(brand))
    if active is not None:
        stmt = stmt.where(Product.is_active.is_(active))
    if width:
        stmt = stmt.where(Product.width == width)
    if aspect_ratio:
        stmt = stmt.where(Product.aspect_ratio == aspect_ratio)
    if rim_diameter:
        stmt = stmt.where(Product.rim_diameter == rim_diameter)
    return list(db.execute(stmt.order_by(Product.sku).limit(limit).offset(offset)).scalars())


def create_product(db: Session, actor: User, data: ProductCreate) -> Product:
    product = Product(**data.model_dump())
    flush_or_conflict(db, product, "A product with this SKU or barcode already exists")
    record_audit(db, actor_id=actor.id, action="product.create", entity_type="product", entity_id=product.id,
                 summary=f"Created product {product.sku}")
    return product


def update_product(db: Session, actor: User, product_id: int, data: ProductUpdate) -> Product:
    product = get_product(db, product_id)
    changes = data.model_dump(exclude_unset=True)
    before = {k: str(getattr(product, k)) for k in changes}
    for k, v in changes.items():
        setattr(product, k, v)
    flush_or_conflict(db, None, "Barcode already in use")
    record_audit(db, actor_id=actor.id, action="product.update", entity_type="product", entity_id=product.id,
                 summary=f"Updated product {product.sku}",
                 details={"before": before, "after": {k: str(v) for k, v in changes.items()}})
    return product


def list_tax_rates(db: Session) -> list[TaxRate]:
    return list(db.execute(select(TaxRate).order_by(TaxRate.code)).scalars())


def default_tax_rate(db: Session) -> TaxRate | None:
    return db.execute(select(TaxRate).where(TaxRate.is_default.is_(True), TaxRate.is_active.is_(True))).scalar_one_or_none()


def upsert_tax_rate(db: Session, actor: User, data: TaxRateIn, tax_rate_id: int | None = None) -> TaxRate:
    if data.is_default:
        db.execute(update(TaxRate).where(TaxRate.id != (tax_rate_id or 0)).values(is_default=False))
    if tax_rate_id is None:
        rate = TaxRate(**data.model_dump())
    else:
        rate = db.get(TaxRate, tax_rate_id)
        if rate is None:
            raise NotFoundError("Tax rate not found")
        for k, v in data.model_dump().items():
            setattr(rate, k, v)
    flush_or_conflict(db, rate, "Tax code already exists")
    record_audit(db, actor_id=actor.id, action="tax_rate.save", entity_type="tax_rate", entity_id=rate.id,
                 summary=f"Saved tax rate {rate.code} = {rate.rate}")
    return rate
