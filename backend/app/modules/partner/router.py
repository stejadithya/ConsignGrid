"""Website stock API (server-to-server, API key) and the administrators' key management."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.permissions import P
from app.modules.identity.deps import DB, NotAuthenticatedError, require
from app.modules.identity.models import User
from app.modules.partner import service
from app.modules.partner.models import PartnerApiKey

router = APIRouter(tags=["partner"])

MAX_SKUS = 100
# The website may reuse an answer for up to a minute; it is computed live on every request that reaches the API.
CACHE_CONTROL = "private, max-age=60"


# --- Website stock API --------------------------------------------------------------------------------------------

def partner_key(db: DB, x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None) -> PartnerApiKey:
    """Only the X-API-Key header is accepted: no session cookie, no staff login."""
    key = service.authenticate(db, x_api_key)
    if key is None:
        raise NotAuthenticatedError("A valid X-API-Key header is required", code="invalid_api_key")
    return key


PartnerKey = Annotated[PartnerApiKey, Depends(partner_key)]


class StockItem(BaseModel):
    sku: str
    name: str
    size: str
    status: str = Field(description="IN_STOCK, LOW or OUT (warehouse stock only)")


class StockList(BaseModel):
    generated_at: datetime
    items: list[StockItem]
    unknown_skus: list[str] = Field(default_factory=list, description="Requested SKUs not in the catalogue")


@router.get("/partner/v1/stock", response_model=StockList)
def partner_stock(db: DB, _: PartnerKey, response: Response,
                  sku: Annotated[list[str] | None, Query(description="Limit to these SKUs (up to 100)")] = None):
    if sku is not None and len(sku) > MAX_SKUS:
        raise BusinessRuleError(f"Ask for at most {MAX_SKUS} SKUs per call, or call without sku for all of them")
    items, unknown = service.stock_statuses(db, get_settings().partner_low_stock_threshold, sku)
    db.commit()   # last_used_at
    response.headers["Cache-Control"] = CACHE_CONTROL
    return StockList(generated_at=datetime.now(UTC), items=[StockItem(**i.__dict__) for i in items], unknown_skus=unknown)


@router.get("/partner/v1/stock/{sku}", response_model=StockItem)
def partner_stock_one(sku: str, db: DB, _: PartnerKey, response: Response):
    items, _unknown = service.stock_statuses(db, get_settings().partner_low_stock_threshold, [sku])
    db.commit()   # last_used_at
    if not items:
        raise NotFoundError(f"Unknown SKU {sku}")
    response.headers["Cache-Control"] = CACHE_CONTROL
    return StockItem(**items[0].__dict__)


# --- Key management (Administrators) -------------------------------------------------------------------------------

class KeyIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class KeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    key_prefix: str
    created_at: datetime
    created_by: str | None = None
    last_used_at: datetime | None
    revoked_at: datetime | None


class KeyCreated(KeyOut):
    key: str = Field(description="The full key. Shown only in this response; store it in the website's server settings.")


Manager = Annotated[User, Depends(require(P.PARTNER_KEYS_MANAGE))]


@router.get("/partner-keys", response_model=list[KeyOut])
def list_keys(db: DB, _: Manager):
    return [KeyOut.model_validate(k).model_copy(update={"created_by": name}) for k, name in service.list_keys(db)]


@router.post("/partner-keys", response_model=KeyCreated, status_code=201)
def create_key(data: KeyIn, db: DB, user: Manager):
    key, raw = service.create_key(db, user, data.name)
    db.commit()
    return KeyCreated(**KeyOut.model_validate(key).model_dump(exclude={"created_by"}), created_by=user.full_name, key=raw)


@router.post("/partner-keys/{key_id}/revoke", response_model=KeyOut)
def revoke_key(key_id: int, db: DB, user: Manager):
    key = service.revoke_key(db, user, key_id)
    db.commit()
    return KeyOut.model_validate(key)
