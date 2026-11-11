from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.industry import vocab
from app.core.permissions import P
from app.modules.customers.models import Reseller
from app.modules.identity.deps import DB, has, require
from app.modules.identity.models import User
from app.modules.identity.scoping import ensure_reseller_access, scoped_reseller_id
from app.modules.reporting import dealer_sku as dealer_sku_report
from app.modules.reporting import service

router = APIRouter(prefix="/reports", tags=["reporting"])


def _json(data) -> JSONResponse:
    """Money is serialised as decimal strings (never floats), consistent with the typed endpoints."""
    return JSONResponse(jsonable_encoder(data, custom_encoder={Decimal: str}))
Reader = Annotated[User, Depends(require(P.REPORT_READ))]


def _staff(user: User) -> None:
    if user.is_reseller_user:
        raise PermissionDeniedError(f"Not available to {vocab.partner} users")


def _scope(user: User, reseller_id: int | None) -> int | None:
    restricted = scoped_reseller_id(user)
    if restricted is not None:
        if reseller_id is not None and reseller_id != restricted:
            raise NotFoundError(f"{vocab.Partner} not found")
        return restricted
    return reseller_id


@router.get("/dashboard")
def dashboard(db: DB, user: Reader):
    return _json(service.dashboard(db, scoped_reseller_id(user)))


@router.get("/consignment-stock")
def consignment_stock(db: DB, user: Reader, reseller_id: int | None = None, location_id: int | None = None,
                      brand: str | None = None, sku: str | None = None, width: int | None = None,
                      aspect_ratio: int | None = None, rim_diameter: float | None = None,
                      availability: str | None = None):
    rid = _scope(user, reseller_id)
    if location_id is not None and user.is_reseller_user:
        from app.modules.customers.service import get_location_scoped
        get_location_scoped(db, user, location_id)
    return _json(service.consignment_stock(db, reseller_id=rid, location_id=location_id, brand=brand, sku=sku,
                                     width=width, aspect_ratio=aspect_ratio, rim_diameter=rim_diameter,
                                     availability=availability, include_value=has(user, P.COST_READ)))


@router.get("/backorders")
def backorders(db: DB, user: Reader, reseller_id: int | None = None, product_id: int | None = None,
               reason: str | None = None, priority: str | None = None, awaiting_supply_only: bool = False):
    return _json(service.backorders(db, reseller_id=_scope(user, reseller_id), product_id=product_id, reason=reason,
                              priority=priority, include_fully_allocated=not awaiting_supply_only))


@router.get("/resellers/{reseller_id}/transactions")
def reseller_transactions(reseller_id: int, db: DB, user: Reader, location_id: int | None = None,
                          product_id: int | None = None, date_from: date | None = None, date_to: date | None = None):
    ensure_reseller_access(user, reseller_id, vocab.Partner)
    if db.get(Reseller, reseller_id) is None:
        raise NotFoundError(f"{vocab.Partner} not found")
    return _json(service.reseller_history(db, reseller_id, location_id=location_id, product_id=product_id,
                                          date_from=date_from, date_to=date_to,
                                          redact_counterparties=user.is_reseller_user))


@router.get("/warehouse-availability")
def warehouse_availability(db: DB, user: Reader):
    _staff(user)
    return _json(service.warehouse_availability(db))


@router.get("/demand-by-sku")
def demand_by_sku(db: DB, user: Reader):
    _staff(user)
    return _json(service.demand_by_sku(db))


@router.get("/uninvoiced-sales")
def uninvoiced(db: DB, user: Reader):
    _staff(user)
    return _json(service.uninvoiced_summary(db))


@router.get("/stocktake-discrepancies")
def stocktake_discrepancies(db: DB, user: Reader, reseller_id: int | None = None):
    return _json(service.stocktake_discrepancies(db, _scope(user, reseller_id)))


@router.get("/consignment-ageing")
def consignment_ageing(db: DB, user: Reader):
    _staff(user)
    return _json(service.consignment_ageing(db))


def _dealer_sku(db, user: User, reseller_id, location_id, date_from, date_to) -> dict:
    """Staff see every dealer; a dealer sees only their own shops (404 for anything else)."""
    rid = _scope(user, reseller_id)
    if location_id is not None and user.is_reseller_user:
        from app.modules.customers.service import get_location_scoped
        get_location_scoped(db, user, location_id)
    return dealer_sku_report.dealer_sku(db, reseller_id=rid, location_id=location_id, date_from=date_from,
                                        date_to=date_to)


@router.get("/dealer-sku")
def dealer_sku(db: DB, user: Reader, reseller_id: int | None = None, location_id: int | None = None,
               date_from: date | None = None, date_to: date | None = None):
    """By dealer, by SKU (finding 31): stock, on the way, waiting, sold and invoiced in the period. Units only."""
    return _json(_dealer_sku(db, user, reseller_id, location_id, date_from, date_to))


@router.get("/dealer-sku.xlsx")
def dealer_sku_xlsx(db: DB, user: Reader, reseller_id: int | None = None, location_id: int | None = None,
                    date_from: date | None = None, date_to: date | None = None):
    report = _dealer_sku(db, user, reseller_id, location_id, date_from, date_to)
    name = f"{get_settings().file_prefix}-by-{vocab.partner}-by-SKU-{report['date_from']:%Y%m%d}-{report['date_to']:%Y%m%d}.xlsx"
    return Response(content=dealer_sku_report.to_xlsx(report),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/stock-corrections")
def stock_corrections(db: DB, user: Reader, reseller_id: int | None = None,
                      date_from: date | None = None, date_to: date | None = None):
    """Every initial stock correction, one row per tyre changed (staff only), newest first."""
    _staff(user)
    return _json(service.stock_corrections(db, reseller_id, date_from, date_to))
