"""Website stock API: API keys and warehouse stock status bands. Read-only on stock; services never commit."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product
from app.modules.customers.models import Location, LocationType
from app.modules.identity.models import User
from app.modules.inventory.models import StockBalance
from app.modules.partner.models import PartnerApiKey

KEY_PREFIX = "tg_live_"
# last_used_at is a guide for administrators, so it is written at most once a minute (not on every call).
LAST_USED_GRANULARITY = timedelta(minutes=1)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_key(db: Session, actor: User, name: str) -> tuple[PartnerApiKey, str]:
    """Returns the stored key and the full key, which is never stored and cannot be shown again."""
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    key = PartnerApiKey(name=name.strip(), key_prefix=raw[: len(KEY_PREFIX) + 4], key_hash=_hash(raw),
                        created_by_user_id=actor.id)
    db.add(key)
    db.flush()
    record_audit(db, actor_id=actor.id, action="partner_key.create", entity_type="partner_api_key", entity_id=key.id,
                 summary=f"Website access key created: {key.name} ({key.key_prefix}…)")
    return key, raw


def revoke_key(db: Session, actor: User, key_id: int) -> PartnerApiKey:
    key = db.get(PartnerApiKey, key_id)
    if key is None:
        raise NotFoundError("Key not found")
    if key.revoked_at is not None:
        raise ConflictError("This key is already revoked")
    key.revoked_at = datetime.now(UTC)
    key.revoked_by_user_id = actor.id
    record_audit(db, actor_id=actor.id, action="partner_key.revoke", entity_type="partner_api_key", entity_id=key.id,
                 summary=f"Website access key revoked: {key.name} ({key.key_prefix}…)")
    db.flush()
    return key


def list_keys(db: Session) -> list[tuple[PartnerApiKey, str | None]]:
    rows = db.execute(select(PartnerApiKey, User.full_name).join(User, User.id == PartnerApiKey.created_by_user_id)
                      .order_by(PartnerApiKey.revoked_at.is_not(None), PartnerApiKey.created_at.desc())).all()
    return [(k, n) for k, n in rows]


def authenticate(db: Session, raw: str | None) -> PartnerApiKey | None:
    """The active key matching `raw`, or None. Keys are looked up by hash, so the raw key is never compared."""
    if not raw or not raw.startswith(KEY_PREFIX):
        return None
    key = db.execute(select(PartnerApiKey).where(PartnerApiKey.key_hash == _hash(raw))).scalar_one_or_none()
    if key is None or key.revoked_at is not None:
        return None
    now = datetime.now(UTC)
    if key.last_used_at is None or now - key.last_used_at >= LAST_USED_GRANULARITY:
        key.last_used_at = now
        db.flush()
    return key


@dataclass
class StockStatus:
    sku: str
    name: str
    size: str
    status: str


def band(available: int, low_threshold: int, active: bool = True) -> str:
    if not active or available <= 0:
        return "OUT"
    return "LOW" if available <= low_threshold else "IN_STOCK"


def stock_statuses(db: Session, low_threshold: int, skus: list[str] | None = None) -> tuple[list[StockStatus], list[str]]:
    """Warehouse status bands per SKU (available = on hand − reserved − blocked, over active warehouse locations).

    Without `skus`: every active product. With `skus`: those products, active or not (inactive ones are OUT), plus
    the SKUs TyreGrow does not know.
    """
    available = (
        select(StockBalance.product_id,
               func.sum(StockBalance.on_hand - StockBalance.reserved - StockBalance.blocked).label("available"))
        .join(Location, Location.id == StockBalance.location_id)
        .where(Location.type == LocationType.WAREHOUSE, Location.is_active.is_(True))
        .group_by(StockBalance.product_id)
        .subquery()
    )
    q = (select(Product, func.coalesce(available.c.available, 0))
         .outerjoin(available, available.c.product_id == Product.id).order_by(Product.sku))
    q = q.where(Product.sku.in_(skus)) if skus is not None else q.where(Product.is_active.is_(True))
    out = [StockStatus(sku=p.sku, name=f"{p.brand} {p.pattern}", size=f"{p.size_display} {p.load_index}{p.speed_rating}",
                       status=band(int(avail), low_threshold, p.is_active))
           for p, avail in db.execute(q).all()]
    found = {s.sku for s in out}
    unknown = [s for s in dict.fromkeys(skus or []) if s not in found]
    return out, unknown
