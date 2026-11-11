import hmac
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import PermissionDeniedError
from app.core.lookups import Names
from app.core.permissions import P
from app.modules.identity.deps import DB, require
from app.modules.identity.models import User
from app.modules.invoicing.models import Invoice
from app.modules.stocktakes import schedule as check_schedule
from app.modules.stocktakes import service
from app.modules.stocktakes.models import Stocktake, StocktakeStatus

router = APIRouter(prefix="/stocktakes", tags=["stocktakes"])
Reader = Annotated[User, Depends(require(P.INVENTORY_READ))]
Recorder = Annotated[User, Depends(require(P.STOCKTAKE_RECORD))]


class CountIn(BaseModel):
    product_id: int
    counted_qty: int = Field(ge=0, le=100000)
    counted_damaged_qty: int = Field(default=0, ge=0)
    notes: str | None = None


class StocktakeCreate(BaseModel):
    location_id: int
    count_date: date
    notes: str | None = None
    counts: list[CountIn] = Field(default_factory=list)


class CountsIn(BaseModel):
    counts: list[CountIn] = Field(min_length=1)


class ClassifyIn(BaseModel):
    qty_sold: int = Field(ge=0)
    qty_missing: int = Field(ge=0)
    notes: str | None = None


class ConfirmLineIn(BaseModel):
    line_id: int
    qty_sold: int = Field(ge=0)
    qty_missing: int = Field(ge=0)


class ConfirmIn(BaseModel):
    lines: list[ConfirmLineIn] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=2000)
    on_behalf_reason: str | None = Field(default=None, max_length=500)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class RecheckIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class DisputeIn(BaseModel):
    message: str = Field(min_length=3, max_length=2000)


class ContactOut(BaseModel):
    role: str
    name: str
    email: str
    phone: str | None


class LineOut(BaseModel):
    id: int
    product_id: int
    sku: str | None
    product_name: str | None
    expected_qty: int | None
    expected_blocked_qty: int | None
    counted_qty: int
    counted_damaged_qty: int
    variance: int | None
    shortage: int
    qty_sold: int
    qty_missing: int
    classified: bool
    notes: str | None
    qty_held: int = 0


class StocktakeOut(BaseModel):
    id: int
    number: str
    location_id: int
    location_code: str | None
    reseller_id: int
    reseller_name: str | None
    count_date: date
    counted_by: str | None
    status: StocktakeStatus
    submitted_at: datetime | None
    approved_by: str | None
    approved_at: datetime | None
    sale_id: int | None
    notes: str | None
    total_variance: int
    lines: list[LineOut]
    total_shortage: int = 0
    confirm_due_at: datetime | None = None
    overdue: bool = False
    reminder_count: int = 0
    last_reminded_at: datetime | None = None
    confirmed_on_behalf_reason: str | None = None
    invoice_id: int | None = None
    invoice_number: str | None = None
    # Who and where (finding 27): the dealer and shop by name, not only the code.
    account_ref: str | None = None
    location_name: str | None = None
    location_address: str | None = None
    location_city: str | None = None
    sales_rep: str | None = None
    # The find window (release 1.11, D3).
    find_days: int | None = None
    recheck_requested_at: datetime | None = None
    recheck_requested_by: str | None = None
    recheck_note: str | None = None
    disputed_at: datetime | None = None
    disputed_by: str | None = None
    dispute_note: str | None = None
    recount_of_id: int | None = None
    recount_of_number: str | None = None
    superseded_by_id: int | None = None
    superseded_by_number: str | None = None


def stocktakes_out(db, sts: list[Stocktake]) -> list[StocktakeOut]:
    inv_ids = {s.invoice_id for s in sts if s.invoice_id}
    inv_numbers = dict(db.execute(select(Invoice.id, Invoice.number).where(Invoice.id.in_(inv_ids))).all()) \
        if inv_ids else {}
    now = datetime.now(UTC)
    names = Names(db)
    for s in sts:
        names.add("location", s.location_id).add("reseller", s.reseller_id)
        names.add("user", s.counted_by_user_id, s.approved_by_user_id, s.recheck_requested_by_user_id,
                  s.disputed_by_user_id).add("product", *[ln.product_id for ln in s.lines])
    names.resolve()
    ids = [s.id for s in sts]
    links = {sid: (rid, num) for sid, rid, num in db.execute(
        select(Stocktake.recount_of_id, Stocktake.id, Stocktake.number).where(Stocktake.recount_of_id.in_(ids)))
        .all()} if ids else {}
    of_ids = {s.recount_of_id for s in sts if s.recount_of_id}
    of_numbers = dict(db.execute(select(Stocktake.id, Stocktake.number).where(Stocktake.id.in_(of_ids))).all()) \
        if of_ids else {}
    days = get_settings().stocktake_find_days
    for s in sts:
        r = names.resellers.get(s.reseller_id)
        names.add("user", r.sales_rep_user_id if r else None)
    names.resolve()

    def where(s):
        loc, r = names.locations.get(s.location_id), names.resellers.get(s.reseller_id)
        address = ", ".join(x for x in (loc.address_line1, loc.address_line2) if x) if loc else None
        return dict(account_ref=r.account_ref if r else None, location_name=loc.name if loc else None,
                    location_address=address or None, location_city=loc.city if loc else None,
                    sales_rep=names.user_name(r.sales_rep_user_id) if r else None)

    return [
        StocktakeOut(
            **where(s),
            id=s.id, number=s.number, location_id=s.location_id, location_code=names.loc_code(s.location_id),
            reseller_id=s.reseller_id, reseller_name=names.reseller_name(s.reseller_id), count_date=s.count_date,
            counted_by=names.user_name(s.counted_by_user_id), status=s.status, submitted_at=s.submitted_at,
            approved_by=names.user_name(s.approved_by_user_id), approved_at=s.approved_at, sale_id=s.sale_id,
            notes=s.notes, total_variance=sum(ln.variance or 0 for ln in s.lines),
            total_shortage=sum(ln.shortage for ln in s.lines), confirm_due_at=s.confirm_due_at,
            overdue=service.overdue(s, now), reminder_count=s.reminder_count, last_reminded_at=s.last_reminded_at,
            confirmed_on_behalf_reason=s.confirmed_on_behalf_reason, invoice_id=s.invoice_id,
            invoice_number=inv_numbers.get(s.invoice_id), find_days=days,
            recheck_requested_at=s.recheck_requested_at, recheck_requested_by=names.user_name(s.recheck_requested_by_user_id),
            recheck_note=s.recheck_note, disputed_at=s.disputed_at, disputed_by=names.user_name(s.disputed_by_user_id),
            dispute_note=s.dispute_note, recount_of_id=s.recount_of_id, recount_of_number=of_numbers.get(s.recount_of_id),
            superseded_by_id=links.get(s.id, (None, None))[0], superseded_by_number=links.get(s.id, (None, None))[1],
            lines=[LineOut(
                id=ln.id, product_id=ln.product_id, sku=names.sku(ln.product_id),
                product_name=names.product_name(ln.product_id), expected_qty=ln.expected_qty,
                expected_blocked_qty=ln.expected_blocked_qty, counted_qty=ln.counted_qty,
                counted_damaged_qty=ln.counted_damaged_qty, variance=ln.variance, shortage=ln.shortage,
                qty_sold=ln.qty_sold, qty_missing=ln.qty_missing,
                classified=ln.qty_sold + ln.qty_missing == ln.shortage, notes=ln.notes, qty_held=ln.qty_held,
            ) for ln in s.lines],
        )
        for s in sts
    ]


def _counts(items: list[CountIn]) -> list[service.CountInput]:
    return [service.CountInput(**c.model_dump()) for c in items]


@router.get("", response_model=list[StocktakeOut])
def list_stocktakes(db: DB, user: Reader, reseller_id: int | None = None, location_id: int | None = None,
                    status: StocktakeStatus | None = None):
    return stocktakes_out(db, service.list_stocktakes(db, user, reseller_id=reseller_id, location_id=location_id,
                                                      status=status))


@router.get("/awaiting-confirmation", response_model=list[StocktakeOut])
def awaiting_confirmation(db: DB, user: Reader):
    """Stock checks with shortages the reseller has not yet confirmed (dashboards highlight overdue ones)."""
    return stocktakes_out(db, service.awaiting_confirmation(db, user))


@router.get("/auto-invoice/cron", include_in_schema=False)
def auto_invoice_cron(db: DB, authorization: Annotated[str | None, Header()] = None):
    """Daily: invoice tyres not found within the find window. Called by Vercel Cron with "Bearer <CRON_SECRET>"."""
    secret = get_settings().cron_secret
    if not secret or not hmac.compare_digest(authorization or "", f"Bearer {secret}"):
        raise PermissionDeniedError("Not allowed")
    invoiced = service.auto_invoice_due(db)
    reminded = service.send_due_reminders(db)
    check_schedule.send_schedule_reminders(db)   # stock checks due today / overdue (UAT round 2)
    db.commit()
    return {"invoiced": invoiced, "reminded": reminded}


class ScheduleRowOut(BaseModel):
    location_id: int
    location_code: str
    shop_name: str
    city: str | None
    reseller_id: int
    reseller_name: str
    sales_rep_user_id: int | None
    sales_rep_name: str | None
    last_count_on: date | None
    due_on: date
    status: str
    days_overdue: int
    moved_to: date | None
    moved_reason: str | None
    moved_by: str | None


class RescheduleIn(BaseModel):
    date: date
    reason: str = Field(min_length=3, max_length=500)


@router.get("/schedule", response_model=list[ScheduleRowOut])
def stock_check_schedule(db: DB, user: Reader, reseller_id: int | None = None):
    """Every active dealer shop with its next stock check: overdue, due today, soon or fine (staff only)."""
    return [ScheduleRowOut(**asdict(r)) for r in check_schedule.schedule(db, user, reseller_id=reseller_id)]


@router.post("/schedule/{location_id}/reschedule", response_model=ScheduleRowOut)
def reschedule_stock_check(location_id: int, data: RescheduleIn, db: DB, user: Recorder):
    """Move a shop's next stock check up to 14 days ahead, with a reason (Sales Rep, Warehouse or Relationship Manager)."""
    row = check_schedule.reschedule(db, user, location_id, data.date, data.reason)
    db.commit()
    return ScheduleRowOut(**asdict(row))


@router.get("/{stocktake_id}/contacts", response_model=list[ContactOut])
def contacts(stocktake_id: int, db: DB, user: Reader):
    """Who to call about this stock check: the Warehouse and Relationship Managers and the dealer's sales rep."""
    return service.contacts(db, service.get_stocktake(db, user, stocktake_id))


@router.get("/{stocktake_id}", response_model=StocktakeOut)
def get_stocktake(stocktake_id: int, db: DB, user: Reader):
    return stocktakes_out(db, [service.get_stocktake(db, user, stocktake_id)])[0]


@router.post("", response_model=StocktakeOut, status_code=201)
def create(data: StocktakeCreate, db: DB, user: Recorder):
    st = service.create(db, user, location_id=data.location_id, count_date=data.count_date,
                        counts=_counts(data.counts), notes=data.notes)
    db.commit()
    return stocktakes_out(db, [service.get_stocktake(db, user, st.id)])[0]


@router.put("/{stocktake_id}/counts", response_model=StocktakeOut)
def update_counts(stocktake_id: int, data: CountsIn, db: DB, user: Recorder):
    service.update_counts(db, user, stocktake_id, _counts(data.counts))
    db.commit()
    return stocktakes_out(db, [service.get_stocktake(db, user, stocktake_id)])[0]


@router.post("/{stocktake_id}/submit", response_model=StocktakeOut)
def submit(stocktake_id: int, db: DB, user: Recorder):
    service.submit(db, user, stocktake_id)
    db.commit()
    return stocktakes_out(db, [service.get_stocktake(db, user, stocktake_id)])[0]


@router.post("/{stocktake_id}/lines/{line_id}/classify", response_model=StocktakeOut)
def classify(stocktake_id: int, line_id: int, data: ClassifyIn, db: DB, user: Recorder):
    service.classify(db, user, stocktake_id, line_id, qty_sold=data.qty_sold, qty_missing=data.qty_missing,
                     notes=data.notes)
    db.commit()
    return stocktakes_out(db, [service.get_stocktake(db, user, stocktake_id)])[0]


@router.post("/{stocktake_id}/confirm", response_model=StocktakeOut)
def confirm(stocktake_id: int, data: ConfirmIn, db: DB, user: Reader):
    """Reseller confirms shortages as sold / missing (staff: on the reseller's behalf, with a reason)."""
    service.confirm(db, user, stocktake_id,
                    [service.Classification(ln.line_id, ln.qty_sold, ln.qty_missing) for ln in data.lines],
                    notes=data.notes, on_behalf_reason=data.on_behalf_reason)
    db.commit()
    return stocktakes_out(db, [service.get_stocktake(db, user, stocktake_id)])[0]


@router.post("/{stocktake_id}/request-recheck", response_model=StocktakeOut)
def request_recheck(stocktake_id: int, data: RecheckIn, db: DB, user: Reader):
    """The dealer found the tyres: "please re-check" (pauses the find window)."""
    service.request_recheck(db, user, stocktake_id, data.note)
    db.commit()
    return stocktakes_out(db, [service.get_stocktake(db, user, stocktake_id)])[0]


@router.post("/{stocktake_id}/dispute", response_model=StocktakeOut)
def dispute(stocktake_id: int, data: DisputeIn, db: DB, user: Reader):
    """The dealer disagrees with the count (pauses the find window; the WM and RM follow up)."""
    service.dispute(db, user, stocktake_id, data.message)
    db.commit()
    return stocktakes_out(db, [service.get_stocktake(db, user, stocktake_id)])[0]


@router.post("/{stocktake_id}/recount", response_model=StocktakeOut, status_code=201)
def recount(stocktake_id: int, db: DB, user: Recorder):
    """Start a re-count: the original is superseded and a new draft for the same shop is returned."""
    new = service.start_recount(db, user, stocktake_id)
    db.commit()
    return stocktakes_out(db, [service.get_stocktake(db, user, new.id)])[0]


@router.post("/{stocktake_id}/approve", response_model=StocktakeOut)
def approve(stocktake_id: int, db: DB, user: Annotated[User, Depends(require(P.STOCKTAKE_APPROVE))]):
    service.approve(db, user, stocktake_id)
    db.commit()
    return stocktakes_out(db, [service.get_stocktake(db, user, stocktake_id)])[0]


@router.post("/{stocktake_id}/cancel", response_model=StocktakeOut)
def cancel(stocktake_id: int, data: ReasonIn, db: DB, user: Recorder):
    service.cancel(db, user, stocktake_id, data.reason)
    db.commit()
    return stocktakes_out(db, [service.get_stocktake(db, user, stocktake_id)])[0]
