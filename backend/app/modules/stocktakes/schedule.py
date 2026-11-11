"""Stock check schedule (UAT round 2, journey 9).

Every dealer shop is due a stock check STOCK_CHECK_EVERY_DAYS (30) after its last count (or after it was added, if
never counted). The Sales Rep, Warehouse Manager or Relationship Manager can move a due check up to
STOCK_CHECK_MOVE_DAYS (14) ahead, with a reason. A daily job reminds the rep on the due date and tells the
Warehouse and Relationship Managers, weekly, about shops whose check is overdue.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.core.industry import vocab
from app.core.permissions import Role
from app.modules.audit.service import record_audit
from app.modules.customers.models import Location, LocationType, Reseller, ResellerStatus
from app.modules.identity.models import User
from app.modules.notifications.service import notify_users, staff_in_roles
from app.modules.stocktakes.models import StockCheckSchedule, Stocktake, StocktakeStatus

_NOT_A_COUNT = (StocktakeStatus.DRAFT, StocktakeStatus.CANCELLED)
SOON_DAYS = 7


@dataclass
class ScheduleRow:
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
    status: str                 # OVERDUE, DUE (today), SOON (within 7 days), OK
    days_overdue: int
    moved_to: date | None
    moved_reason: str | None
    moved_by: str | None


def shop_label(dealer: str, shop: str) -> str:
    """Dealer name first, then the shop, without repeating the dealer ("Roskill Tyres — Main shop")."""
    rest = shop[len(dealer):].strip(" —–-,·") if shop.lower().startswith(dealer.lower()) else shop
    return f"{dealer} — {rest}" if rest else dealer


def _today() -> date:
    return datetime.now(UTC).date()


def _rows(db: Session, today: date, *, reseller_id: int | None = None, location_id: int | None = None
          ) -> list[tuple[ScheduleRow, StockCheckSchedule | None]]:
    every = get_settings().stock_check_every_days
    q = (select(Location, Reseller).join(Reseller, Reseller.id == Location.reseller_id)
         .where(Location.type == LocationType.CONSIGNMENT, Location.is_active.is_(True),
                Reseller.status == ResellerStatus.ACTIVE))
    if reseller_id is not None:
        q = q.where(Reseller.id == reseller_id)
    if location_id is not None:
        q = q.where(Location.id == location_id)
    shops = db.execute(q.order_by(Reseller.business_name, Location.name)).all()
    if not shops:
        return []
    ids = [loc.id for loc, _ in shops]
    last = dict(db.execute(select(Stocktake.location_id, func.max(Stocktake.count_date))
                           .where(Stocktake.location_id.in_(ids), Stocktake.status.not_in(_NOT_A_COUNT))
                           .group_by(Stocktake.location_id)).all())
    plans = {s.location_id: s for s in db.execute(select(StockCheckSchedule)
                                                  .where(StockCheckSchedule.location_id.in_(ids))).scalars()}
    user_ids = {r.sales_rep_user_id for _, r in shops} | {p.moved_by_user_id for p in plans.values()}
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids - {None})))
                 .all()) if user_ids - {None} else {}
    out = []
    for loc, reseller in shops:
        counted = last.get(loc.id)
        due = (counted or loc.created_at.date()) + timedelta(days=every)
        plan = plans.get(loc.id)
        # A move holds until the shop is counted again.
        moved = plan.next_check_on if plan and plan.next_check_on and not (
            counted and plan.moved_at and counted >= plan.moved_at.date()) else None
        if moved:
            due = moved
        status = "OVERDUE" if today > due else "DUE" if today == due else "SOON" if (due - today).days <= SOON_DAYS else "OK"
        out.append((ScheduleRow(
            location_id=loc.id, location_code=loc.code, shop_name=loc.name, city=loc.city, reseller_id=reseller.id,
            reseller_name=reseller.business_name, sales_rep_user_id=reseller.sales_rep_user_id,
            sales_rep_name=names.get(reseller.sales_rep_user_id), last_count_on=counted, due_on=due, status=status,
            days_overdue=max(0, (today - due).days), moved_to=moved, moved_reason=plan.moved_reason if moved else None,
            moved_by=names.get(plan.moved_by_user_id) if moved else None), plan))
    return out


def schedule(db: Session, user: User, *, reseller_id: int | None = None) -> list[ScheduleRow]:
    """Every active dealer shop with its next stock check. Staff only."""
    if user.is_reseller_user:
        raise PermissionDeniedError(f"Not available to {vocab.partner} users")
    return [row for row, _ in _rows(db, _today(), reseller_id=reseller_id)]


def reschedule(db: Session, actor: User, location_id: int, new_date: date, reason: str) -> ScheduleRow:
    """Move a shop's next stock check to a date up to STOCK_CHECK_MOVE_DAYS ahead, with a reason."""
    if actor.is_reseller_user:
        raise PermissionDeniedError(f"Not available to {vocab.partner} users")
    today, limit = _today(), get_settings().stock_check_move_days
    found = _rows(db, today, location_id=location_id)
    if not found:
        raise NotFoundError(f"{vocab.Site} not found")
    row, plan = found[0]
    if actor.role == Role.SALES_REP and row.sales_rep_user_id != actor.id:
        raise PermissionDeniedError(f"{row.reseller_name} is looked after by {row.sales_rep_name or 'another rep'}; "
                                    "ask them, or the Warehouse or Relationship Manager, to move it")
    if not today <= new_date <= today + timedelta(days=limit):
        raise BusinessRuleError(f"Choose a date from today up to {limit} days ahead "
                                f"({(today + timedelta(days=limit)).isoformat()})")
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise BusinessRuleError("Say why the stock check is moved")
    if plan is None:
        plan = StockCheckSchedule(location_id=location_id)
        db.add(plan)
    before = row.due_on
    plan.next_check_on, plan.moved_reason, plan.moved_by_user_id, plan.moved_at = new_date, reason, actor.id, datetime.now(UTC)
    plan.due_notified_on = plan.overdue_notified_on = None     # remind again on the new date
    db.flush()
    where = shop_label(row.reseller_name, row.shop_name)
    record_audit(db, actor_id=actor.id, action="stocktake.reschedule", entity_type="location", entity_id=location_id,
                 reseller_id=row.reseller_id,
                 summary=f"Stock check at {where} moved from {before.isoformat()} to {new_date.isoformat()}: {reason}")
    audience = staff_in_roles(db, Role.WAREHOUSE_MANAGER, Role.RELATIONSHIP_MANAGER) + [row.sales_rep_user_id]
    notify_users(db, audience, f"Stock check moved: {where}",
                 f"{actor.full_name} moved it to {new_date:%d %b %Y} (was due {before:%d %b %Y}). Reason: {reason}",
                 link=f"/resellers/{row.reseller_id}", entity_type="reseller", entity_id=row.reseller_id, exclude=actor.id)
    return _rows(db, today, location_id=location_id)[0][0]


def send_schedule_reminders(db: Session, today: date | None = None) -> dict:
    """Daily: the rep on the due date; the Warehouse and Relationship Managers (and the rep) weekly while overdue."""
    today = today or _today()
    managers = staff_in_roles(db, Role.WAREHOUSE_MANAGER, Role.RELATIONSHIP_MANAGER)
    due = overdue = 0
    for row, plan in _rows(db, today):
        if row.status not in ("DUE", "OVERDUE"):
            continue
        if plan is None:
            plan = StockCheckSchedule(location_id=row.location_id)
            db.add(plan)
        where = shop_label(row.reseller_name, row.shop_name)
        if row.status == "DUE" and plan.due_notified_on != today:
            notify_users(db, [row.sales_rep_user_id], f"Stock check due today: {where}",
                         f"Can't do it today? Move it to another day from the {vocab.partner}'s page (up to 14 days ahead).",
                         link=f"/stocktakes/new?location={row.location_id}", entity_type="reseller", entity_id=row.reseller_id)
            plan.due_notified_on = today
            due += 1
        elif row.status == "OVERDUE" and (plan.overdue_notified_on is None
                                          or (today - plan.overdue_notified_on).days >= 7):
            since = f"{(today - row.last_count_on).days} days" if row.last_count_on else "since it was added"
            notify_users(db, managers + [row.sales_rep_user_id], f"Stock check overdue: {where}",
                         f"No stock check at {where} for {since} (due {row.due_on:%d %b %Y}). "
                         f"Sales rep: {row.sales_rep_name or 'not assigned'}.",
                         link=f"/resellers/{row.reseller_id}", entity_type="reseller", entity_id=row.reseller_id)
            plan.overdue_notified_on = today
            overdue += 1
    db.flush()
    return {"due_reminders": due, "overdue_alerts": overdue}
