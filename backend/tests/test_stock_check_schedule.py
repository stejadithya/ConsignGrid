"""Stock check schedule (UAT round 2, journey 9): due every 30 days, moved up to 14 days ahead with a reason by the
Sales Rep, Warehouse Manager or Relationship Manager; the rep is reminded on the day, and the Warehouse and
Relationship Managers are told when a shop goes 30+ days without a check.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.core.permissions import Role
from app.modules.customers.models import Location
from app.modules.stock_requests.models import Notification
from app.modules.stocktakes import schedule
from tests.factories import make_user, set_stock

pytestmark = pytest.mark.usefixtures("ledger_balanced")
TODAY = datetime.now(UTC).date()


def _row(world, loc, user=None):
    rows = world.api(user or world.warehouse_op).get("/stocktakes/schedule").json()
    return next(r for r in rows if r["location_id"] == loc.id)


def _age(world, loc, days):
    world.db.execute(update(Location).where(Location.id == loc.id)
                     .values(created_at=datetime.now(UTC) - timedelta(days=days)))
    world.db.commit()


def _titles(world, user):
    return {n.title: n.body for n in world.db.execute(select(Notification).where(Notification.user_id == user.id)).scalars()}


def _count(world, loc, product, qty, days_ago=0):
    rep = world.api(world.rep)
    st = rep.post("/stocktakes", {"location_id": loc.id, "count_date": (TODAY - timedelta(days=days_ago)).isoformat(),
                                  "counts": [{"product_id": product.id, "counted_qty": qty}]}).json()
    rep.post(f"/stocktakes/{st['id']}/submit")


def test_due_30_days_after_the_last_count_or_after_the_shop_was_added(world):
    _age(world, world.loc_a, 40)                                  # never counted, added 40 days ago
    r = _row(world, world.loc_a)
    assert (r["status"], r["days_overdue"], r["last_count_on"]) == ("OVERDUE", 10, None)
    assert r["reseller_name"] == "Alpha Tyres" and r["sales_rep_name"] == "Riley Rep"
    set_stock(world.db, world.loc_b, world.p1, 2)
    world.db.commit()
    _count(world, world.loc_b, world.p1, 2, days_ago=10)
    r = _row(world, world.loc_b)
    assert (r["status"], r["due_on"]) == ("OK", (TODAY + timedelta(days=20)).isoformat())
    world.api(world.user_a).get("/stocktakes/schedule", expected=403)


def test_the_rep_moves_it_up_to_14_days_with_a_reason_and_managers_are_told(world):
    _age(world, world.loc_a, 40)
    rep = world.api(world.rep)
    url = f"/stocktakes/schedule/{world.loc_a.id}/reschedule"
    rep.post(url, {"date": (TODAY + timedelta(days=15)).isoformat(), "reason": "Away at a trade show"}, expected=422)
    rep.post(url, {"date": (TODAY - timedelta(days=1)).isoformat(), "reason": "Away at a trade show"}, expected=422)
    rep.post(url, {"date": (TODAY + timedelta(days=5)).isoformat(), "reason": "no"}, expected=422)
    r = rep.post(url, {"date": (TODAY + timedelta(days=5)).isoformat(), "reason": "Shop closed for stocktake week"}).json()
    assert (r["status"], r["moved_to"], r["moved_by"]) == ("SOON", (TODAY + timedelta(days=5)).isoformat(), "Riley Rep")
    assert r["moved_reason"] == "Shop closed for stocktake week" and r["days_overdue"] == 0
    for manager in (world.warehouse_op, world.manager):
        body = _titles(world, manager)["Stock check moved: Alpha Tyres — Main"]
        assert "Riley Rep moved it to" in body and "Shop closed for stocktake week" in body


def test_who_can_move_it(world):
    other = make_user(world.db, Role.SALES_REP, "other.rep@example.com")
    world.db.commit()
    url = f"/stocktakes/schedule/{world.loc_a.id}/reschedule"
    body = {"date": (TODAY + timedelta(days=3)).isoformat(), "reason": "Owner away"}
    world.api(other).post(url, body, expected=403)                   # not this dealer's rep
    world.api(world.user_a).post(url, body, expected=403)            # dealers can't
    world.api(world.warehouse_op).post(url, body)
    world.api(world.manager).post(url, body)


def test_a_count_after_a_move_puts_the_schedule_back_on_30_days(world):
    _age(world, world.loc_a, 40)
    world.api(world.rep).post(f"/stocktakes/schedule/{world.loc_a.id}/reschedule",
                              {"date": (TODAY + timedelta(days=3)).isoformat(), "reason": "Owner away"})
    set_stock(world.db, world.loc_a, world.p1, 1)
    world.db.commit()
    _count(world, world.loc_a, world.p1, 1)
    r = _row(world, world.loc_a)
    assert (r["moved_to"], r["due_on"], r["status"]) == (None, (TODAY + timedelta(days=30)).isoformat(), "OK")


def test_reminders_on_the_day_and_weekly_overdue_alerts(world):
    db = world.db
    _age(world, world.loc_a, 40)                                     # overdue
    world.api(world.warehouse_op).post(f"/stocktakes/schedule/{world.loc_b.id}/reschedule",
                                       {"date": TODAY.isoformat(), "reason": "Do it today"})   # due today
    sent = schedule.send_schedule_reminders(db, TODAY)
    db.commit()
    assert sent == {"due_reminders": 1, "overdue_alerts": 1}
    assert "Stock check due today: Bravo Auto — Main" in _titles(world, world.rep)
    for person in (world.warehouse_op, world.manager, world.rep):
        assert "No stock check at Alpha Tyres — Main" in _titles(world, person)["Stock check overdue: Alpha Tyres — Main"]
    # Not repeated the same day, nor within the week; again a week later.
    assert schedule.send_schedule_reminders(db, TODAY) == {"due_reminders": 0, "overdue_alerts": 0}
    assert schedule.send_schedule_reminders(db, TODAY + timedelta(days=3))["overdue_alerts"] == 1   # Bravo now overdue
    assert schedule.send_schedule_reminders(db, TODAY + timedelta(days=7))["overdue_alerts"] == 1   # Alpha again
    db.commit()


def test_inactive_dealers_are_left_out(world):
    from app.modules.customers.models import ResellerStatus

    world.reseller_c.status = ResellerStatus.CLOSED
    world.db.commit()
    rows = world.api(world.warehouse_op).get("/stocktakes/schedule").json()
    assert world.loc_c.id not in {r["location_id"] for r in rows}
    assert isinstance(date.fromisoformat(rows[0]["due_on"]), date)
