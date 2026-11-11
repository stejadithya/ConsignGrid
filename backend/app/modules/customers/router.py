import base64
import binascii
from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, PermissionDeniedError
from app.core.industry import vocab
from app.core.permissions import P
from app.modules.customers import (
    agreement_files,
    history,
    initial_stock_correction,
    initial_stock_import,
    refs,
    service,
)
from app.modules.customers.models import Location, LocationType, ResellerStatus
from app.modules.customers.schemas import (
    AccountRefPreview,
    AgreementIn,
    AgreementOut,
    CustomerPriceIn,
    CustomerPriceOut,
    DealerShopIn,
    LocationOut,
    ResellerCreate,
    ResellerOut,
    ResellerStatusChange,
    ResellerSummary,
    ResellerUpdate,
    WarehouseIn,
)
from app.modules.identity.deps import DB, CurrentUser, has, require
from app.modules.identity.models import User
from app.modules.inventory.operations import post_opening_balance
from app.modules.inventory.schemas import OpeningBalanceIn

router = APIRouter(tags=["resellers"])


def _can_view_reseller(user: User) -> None:
    # Dealership staff need reseller.read; reseller users may always view their own (scoped in service).
    if not user.is_reseller_user and not has(user, P.RESELLER_READ):
        raise PermissionDeniedError("Missing permission: reseller.read")


@router.get("/resellers", response_model=list[ResellerSummary])
def list_resellers(
    db: DB, user: CurrentUser, q: str | None = None, status: ResellerStatus | None = None,
    sales_rep_user_id: int | None = None,
):
    _can_view_reseller(user)
    return service.list_resellers(db, user, q=q, status=status, sales_rep_user_id=sales_rep_user_id)


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_IMPORT_BYTES = 5 * 1024 * 1024
InitialStocker = Annotated[User, Depends(require(P.RESELLER_INITIAL_STOCK))]


class InitialStockImportIn(BaseModel):
    filename: str | None = Field(default=None, max_length=255)
    content_base64: str = Field(min_length=4)
    commit: bool = False   # False = check only (nothing is changed)


@router.get("/resellers/initial-stock/template")
def initial_stock_template(_: InitialStocker):
    """Blank Excel for an existing dealer's initial stock: SKU Code, Quantity, Shop code."""
    name = f"{get_settings().file_prefix}_Initial_Stock_Template.xlsx"
    return Response(content=initial_stock_import.template(), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/resellers/{reseller_id}/initial-stock/import")
def import_initial_stock(reseller_id: int, data: InitialStockImportIn, db: DB, user: InitialStocker):
    """Check (commit=false) or post (commit=true) a dealer's initial stock from Excel: one opening balance per shop."""
    reseller = service.get_reseller(db, user, reseller_id)
    _initial_stock_allowed(reseller)
    try:
        content = base64.b64decode(data.content_base64.split(",")[-1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BusinessRuleError("The uploaded file could not be decoded.") from exc
    if len(content) > MAX_IMPORT_BYTES:
        raise BusinessRuleError("The file is larger than 5 MB.")
    analysis = initial_stock_import.check(db, reseller, content)
    posted = None
    if data.commit:
        posted = initial_stock_import.commit(db, user, analysis)
        db.commit()
    return {"filename": data.filename, "committed": data.commit, "posted": posted, **analysis}


class AgreementFileIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=4)


class AgreementFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime
    uploaded_by: str | None = None


def _file_out(db, f) -> AgreementFileOut:
    out = AgreementFileOut.model_validate(f)
    u = db.get(User, f.uploaded_by_user_id) if f.uploaded_by_user_id else None
    out.uploaded_by = u.full_name if u else None
    return out


@router.post("/resellers/{reseller_id}/agreement-files", response_model=AgreementFileOut, status_code=201)
def upload_agreement_file(reseller_id: int, data: AgreementFileIn, db: DB,
                          user: Annotated[User, Depends(require(P.RESELLER_WRITE))]):
    """Attach a copy of the signed agreement: PDF, JPG, PNG or WEBP, at most 5 MB (D8)."""
    f = agreement_files.upload(db, user, service.get_reseller(db, user, reseller_id), data.filename, data.content_base64)
    db.commit()
    return _file_out(db, f)


@router.get("/resellers/{reseller_id}/agreement-files", response_model=list[AgreementFileOut])
def list_agreement_files(reseller_id: int, db: DB, user: CurrentUser):
    _can_view_reseller(user)
    service.get_reseller(db, user, reseller_id)   # a dealer may only see their own (404 otherwise)
    return [_file_out(db, f) for f in agreement_files.list_files(db, reseller_id)]


@router.get("/resellers/{reseller_id}/agreement-files/{file_id}")
def download_agreement_file(reseller_id: int, file_id: int, db: DB, user: CurrentUser):
    _can_view_reseller(user)
    service.get_reseller(db, user, reseller_id)
    f = agreement_files.get_file(db, reseller_id, file_id)
    safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in f.filename)
    return Response(content=f.data, media_type=f.content_type,
                    headers={"Content-Disposition": f'inline; filename="{safe}"', "Cache-Control": "private, no-store"})


@router.delete("/resellers/{reseller_id}/agreement-files/{file_id}", status_code=204)
def delete_agreement_file(reseller_id: int, file_id: int, db: DB,
                          user: Annotated[User, Depends(require(P.RESELLER_WRITE))]):
    service.get_reseller(db, user, reseller_id)
    agreement_files.remove(db, user, reseller_id, file_id)
    db.commit()
    return Response(status_code=204)


@router.get("/resellers/account-ref-preview", response_model=AccountRefPreview)
def account_ref_preview(business_name: str, db: DB, _: Annotated[User, Depends(require(P.RESELLER_WRITE))],
                        city: str | None = None):
    """The reference a new dealer would get (D4). The final one is confirmed when the dealer is saved."""
    return AccountRefPreview(account_ref=refs.preview(db, business_name, city))


@router.get("/resellers/{reseller_id}", response_model=ResellerOut)
def get_reseller(reseller_id: int, db: DB, user: CurrentUser):
    _can_view_reseller(user)
    return service.reseller_out(db, service.get_reseller(db, user, reseller_id))


@router.post("/resellers", response_model=ResellerOut, status_code=201)
def create_reseller(data: ResellerCreate, db: DB, user: Annotated[User, Depends(require(P.RESELLER_WRITE))]):
    if data.create_login and not has(user, P.USER_MANAGE):
        raise PermissionDeniedError(f"Missing permission: user.manage (needed to create the {vocab.partner}'s login)")
    r, login = service.create_reseller(db, user, data)
    db.commit()
    out = service.reseller_out(db, service.get_reseller(db, user, r.id))
    out.login = login
    return out


@router.patch("/resellers/{reseller_id}", response_model=ResellerOut)
def update_reseller(
    reseller_id: int, data: ResellerUpdate, db: DB, user: Annotated[User, Depends(require(P.RESELLER_WRITE))]
):
    service.update_reseller(db, user, reseller_id, data)
    db.commit()
    return service.reseller_out(db, service.get_reseller(db, user, reseller_id))


@router.post("/resellers/{reseller_id}/status", response_model=ResellerOut)
def change_status(
    reseller_id: int, data: ResellerStatusChange, db: DB,
    user: Annotated[User, Depends(require(P.RESELLER_WRITE))],
):
    service.change_status(db, user, reseller_id, data)
    db.commit()
    return service.reseller_out(db, service.get_reseller(db, user, reseller_id))


@router.put("/resellers/{reseller_id}/agreement", response_model=AgreementOut)
def save_agreement(
    reseller_id: int, data: AgreementIn, db: DB, user: Annotated[User, Depends(require(P.RESELLER_WRITE))]
):
    a = service.save_agreement(db, user, reseller_id, data)
    db.commit()
    return a


@router.post("/resellers/{reseller_id}/locations", response_model=LocationOut, status_code=201)
def add_location(
    reseller_id: int, data: DealerShopIn, db: DB, user: Annotated[User, Depends(require(P.RESELLER_WRITE))]
):
    loc = service.add_reseller_location(db, user, reseller_id, data)
    db.commit()
    return loc


def _initial_stock_allowed(reseller) -> None:
    """Initial stock is only for a dealer who already held the supplier's stock when added (UAT round 2)."""
    if reseller.joined_with_stock is False:
        raise BusinessRuleError(f"{reseller.business_name} was added as a new {vocab.partner}, so their stock comes from the "
                                "warehouse: create a stock request, which goes for approval and delivery.")


@router.post("/resellers/{reseller_id}/initial-stock", status_code=201)
def add_initial_stock(reseller_id: int, data: OpeningBalanceIn, db: DB,
                      user: Annotated[User, Depends(require(P.RESELLER_INITIAL_STOCK))]):
    """Stock an existing reseller already holds when added to the system: their 'Initial stock (backorder)'."""
    _initial_stock_allowed(service.get_reseller(db, user, reseller_id))
    loc = db.get(Location, data.location_id)
    if loc is None or loc.type != LocationType.CONSIGNMENT or loc.reseller_id != reseller_id:
        raise BusinessRuleError(f"Choose one of this {vocab.partner}'s consignment locations")
    txn = post_opening_balance(db, user, data, reason=f"Initial stock (backorder): held by the {vocab.partner} when added")
    db.commit()
    return {"transaction_number": txn.number, "units": sum(ln.quantity for ln in data.lines)}


@router.get("/resellers/{reseller_id}/prices", response_model=list[CustomerPriceOut])
def list_prices(reseller_id: int, db: DB, user: Annotated[User, Depends(require(P.RESELLER_READ))]):
    out = []
    for price, sku in service.list_prices(db, user, reseller_id):
        o = CustomerPriceOut.model_validate(price)
        o.sku = sku
        out.append(o)
    return out


@router.post("/resellers/{reseller_id}/prices", response_model=CustomerPriceOut, status_code=201)
def add_price(
    reseller_id: int, data: CustomerPriceIn, db: DB, user: Annotated[User, Depends(require(P.PRICING_WRITE))]
):
    price = service.add_price(db, user, reseller_id, data)
    db.commit()
    return price


@router.get("/locations", response_model=list[LocationOut])
def list_locations(
    db: DB, user: Annotated[User, Depends(require(P.INVENTORY_READ))],
    type: Annotated[list[LocationType] | None, Query()] = None,
    reseller_id: int | None = None, active: bool | None = None,
):
    return service.list_locations(db, user, types=type, reseller_id=reseller_id, active=active)


@router.post("/warehouses", response_model=LocationOut, status_code=201)
def create_warehouse(data: WarehouseIn, db: DB, user: Annotated[User, Depends(require(P.LOCATION_MANAGE))]):
    loc = service.create_warehouse(db, user, data)
    db.commit()
    return loc


@router.put("/locations/{location_id}", response_model=LocationOut)
def update_location(
    location_id: int, data: WarehouseIn, db: DB, user: Annotated[User, Depends(require(P.LOCATION_MANAGE))]
):
    loc = service.update_location(db, user, location_id, data)
    db.commit()
    return loc


class StockLineOut(BaseModel):
    product_id: int
    sku: str
    name: str
    quantity: int                 # after any initial stock corrections
    recorded: int | None = None   # as first entered, when a correction changed it


class ArrivalOut(BaseModel):
    occurred_at: datetime
    transaction_number: str
    txn_type: str
    reference_number: str | None


class LastSaleOut(BaseModel):
    id: int
    number: str
    sale_date: date
    units: int


class DealerHistoryOut(BaseModel):
    reseller_id: int
    onboarded_at: datetime
    onboarded_by: str | None
    dealer_type: str
    first_stock: ArrivalOut | None
    onboarding_stock_kind: str | None
    onboarding_stock_at: datetime | None
    onboarding_stock: list[StockLineOut]
    units_sold: int
    sales_count: int
    last_sale: LastSaleOut | None
    corrections: int = 0          # initial stock corrections made


@router.get("/resellers/{reseller_id}/history-summary", response_model=DealerHistoryOut)
def dealer_history(reseller_id: int, db: DB, _: Annotated[User, Depends(require(P.DEALER_HISTORY_READ))]):
    """When the dealer joined and with what stock, their first consignment, and their sales so far (staff only)."""
    return DealerHistoryOut(**asdict(history.dealer_history(db, reseller_id)))


# --- Initial stock corrections (Relationship Manager and Administrator) -------------------------------------------

class CorrectionChangeOut(BaseModel):
    product_id: int
    sku: str
    name: str
    before: int
    after: int


class CorrectionOut(BaseModel):
    transaction_id: int
    transaction_number: str
    corrected_at: datetime
    corrected_by: str | None
    reason: str
    changes: list[CorrectionChangeOut]


class InitialStockLineOut(BaseModel):
    product_id: int
    sku: str
    name: str
    recorded: int
    current: int
    free_now: int


class InitialStockEntryOut(BaseModel):
    transaction_id: int
    transaction_number: str
    recorded_at: datetime
    recorded_by: str | None
    location_id: int
    location_code: str
    location_name: str
    lines: list[InitialStockLineOut]
    corrections: list[CorrectionOut]
    can_correct: bool
    locked_reason: str | None
    correctable_until: datetime | None


class CorrectionLineIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=0, le=100000)   # the correct quantity; 0 removes the tyre from the entry


class InitialStockCorrectionIn(BaseModel):
    lines: list[CorrectionLineIn] = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=5, max_length=500)


Corrector = Annotated[User, Depends(require(P.INITIAL_STOCK_CORRECT))]


@router.get("/resellers/{reseller_id}/initial-stock/entries", response_model=list[InitialStockEntryOut])
def initial_stock_entries(reseller_id: int, db: DB, _: Corrector):
    """The dealer's initial stock entries with their corrections, and whether each can still be corrected."""
    return [InitialStockEntryOut(**asdict(e)) for e in initial_stock_correction.entries(db, reseller_id)]


@router.post("/resellers/{reseller_id}/initial-stock/{transaction_id}/corrections", response_model=CorrectionOut,
             status_code=201)
def correct_initial_stock(reseller_id: int, transaction_id: int, data: InitialStockCorrectionIn, db: DB, user: Corrector):
    """Fix a wrongly entered initial stock: a new correction next to the original, which is never changed."""
    c = initial_stock_correction.correct(db, user, reseller_id, transaction_id,
                                         [(ln.product_id, ln.quantity) for ln in data.lines], data.reason)
    db.commit()
    return CorrectionOut(**asdict(c))
