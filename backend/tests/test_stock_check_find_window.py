"""Release 1.11 — stock checks (findings 27–30, D3): 5 days to find tyres not found; re-check, dispute, re-count,
automatic invoicing at the end of the window; no "missing"; contacts for the dealer."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.modules.invoicing.models import Invoice
from app.modules.replenishment.models import ReplenishmentRequest
from app.modules.sales.models import ConsignmentSale
from app.modules.stocktakes import service as stocktakes
from app.modules.stocktakes.models import Stocktake
from tests.factories import set_stock, set_target

pytestmark = pytest.mark.usefixtures("ledger_balanced")   # every test ends with the ledger reconciled

TODAY = date.today().isoformat()


def _short(world, counted=3, on_hand=5):
    """The rep counts `counted` of `on_hand` tyres at Alpha's shop and submits."""
    set_stock(world.db, world.loc_a, world.p1, on_hand)
    set_target(world.db, world.loc_a, world.p1, on_hand)
    world.db.commit()
    rep = world.api(world.rep)
    st = rep.post("/stocktakes", {"location_id": world.loc_a.id, "count_date": TODAY,
                                  "counts": [{"product_id": world.p1.id, "counted_qty": counted}]}).json()
    return rep.post(f"/stocktakes/{st['id']}/submit").json()


def _ledger_ok(world):
    assert world.api(world.warehouse_op).get("/inventory/reconciliation").json()["balanced"] is True


def _counts(world):
    db = world.db
    return tuple(db.execute(select(func.count()).select_from(m)).scalar_one()
                 for m in (ConsignmentSale, Invoice, ReplenishmentRequest))


def test_a_shortage_is_due_in_five_days_and_shows_who_and_where(world):
    st = _short(world)
    submitted = datetime.fromisoformat(st["submitted_at"])
    assert datetime.fromisoformat(st["confirm_due_at"]) - submitted == timedelta(days=5)
    assert (st["status"], st["total_shortage"], st["find_days"]) == ("AWAITING_RESELLER", 2, 5)
    assert (st["reseller_name"], st["account_ref"], st["location_name"], st["sales_rep"]) == \
        ("Alpha Tyres", "RA", world.loc_a.name, "Riley Rep")
    due = datetime.fromisoformat(st["confirm_due_at"])
    note = next(n for n in world.api(world.user_a).get("/notifications").json()
                if n["title"] == f"Stock check {st['number']}: 2 tyre(s) not found")
    assert note["body"].startswith(
        "2 tyre(s) weren't found at today's stock check. You have 5 days to find them. If you find them, ask for a "
        f"re-check. If not, they'll be invoiced as sold on {due:%d %b %Y}.")
    assert world.bal(world.loc_a, world.p1).blocked == 2


def test_missing_is_refused(world):
    st = _short(world)
    line = st["lines"][0]
    r = world.api(world.user_a).post(f"/stocktakes/{st['id']}/confirm", {
        "lines": [{"line_id": line["id"], "qty_sold": 1, "qty_missing": 1}]}, expected=422).json()
    assert r["detail"] == "In consignment, tyres that aren't found are re-checked or invoiced."


def test_recheck_starts_a_linked_recount_and_releases_the_hold(world):
    st = _short(world)
    dealer, rep, wm = world.api(world.user_a), world.api(world.rep), world.api(world.warehouse_op)
    url = f"/stocktakes/{st['id']}"
    rep.post(f"{url}/request-recheck", {"note": "x"}, expected=403)          # only the dealer asks
    world.api(world.user_b).post(f"{url}/request-recheck", {}, expected=404)
    out = dealer.post(f"{url}/request-recheck", {"note": "They were in the back store"}).json()
    assert out["status"] == "RECHECK_REQUESTED" and out["recheck_note"] == "They were in the back store"
    for user in (world.rep, world.warehouse_op):
        assert any(n["title"] == f"Re-check requested: {st['number']}" for n in world.api(user).get("/notifications").json())
    # Paused: the end of the window does nothing.
    world.db.get(Stocktake, st["id"]).confirm_due_at = datetime.now(UTC) - timedelta(minutes=1)
    world.db.commit()
    before = _counts(world)
    dealer.get("/notifications/unread-count")
    assert _counts(world) == before
    # The rep starts the re-count: the hold is released and a draft for the same shop holds the shortage SKUs.
    dealer.post(f"{url}/recount", expected=403)
    new = rep.post(f"{url}/recount", expected=201).json()
    assert (new["status"], new["recount_of_id"], new["recount_of_number"]) == ("DRAFT", st["id"], st["number"])
    assert new["location_id"] == world.loc_a.id and [ln["product_id"] for ln in new["lines"]] == [world.p1.id]
    old = wm.get(url).json()
    assert (old["status"], old["superseded_by_id"]) == ("SUPERSEDED", new["id"])
    assert world.bal(world.loc_a, world.p1).blocked == 0
    _ledger_ok(world)
    # The tyres turned up: the re-count finds all five and nothing is invoiced.
    rep.put(f"/stocktakes/{new['id']}/counts", {"counts": [{"product_id": world.p1.id, "counted_qty": 5}]})
    done = rep.post(f"/stocktakes/{new['id']}/submit").json()
    assert done["status"] == "APPROVED" and done["invoice_id"] is None
    _ledger_ok(world)


def test_a_dispute_pauses_the_automatic_invoicing(world):
    st = _short(world)
    dealer = world.api(world.user_a)
    dealer.post(f"/stocktakes/{st['id']}/dispute", {"message": "no"}, expected=422)
    out = dealer.post(f"/stocktakes/{st['id']}/dispute", {"message": "Two went back to the warehouse"}).json()
    assert out["status"] == "DISPUTED" and out["dispute_note"] == "Two went back to the warehouse"
    for user in (world.warehouse_op, world.manager):
        assert any(n["title"] == f"Stock check disputed: {st['number']}" for n in world.api(user).get("/notifications").json())
    world.db.get(Stocktake, st["id"]).confirm_due_at = datetime.now(UTC) - timedelta(days=1)
    world.db.commit()
    assert stocktakes.auto_invoice_due(world.db) == 0
    world.db.commit()
    assert world.api(world.manager).get(f"/stocktakes/{st['id']}").json()["status"] == "DISPUTED"
    # Staff resolve it: invoice the shortage on the dealer's behalf, with a reason.
    line = st["lines"][0]
    done = world.api(world.manager).post(f"/stocktakes/{st['id']}/confirm", {
        "lines": [{"line_id": line["id"], "qty_sold": 2, "qty_missing": 0}],
        "on_behalf_reason": "Checked with the warehouse: not returned"}).json()
    assert done["status"] == "APPROVED" and done["invoice_id"]
    _ledger_ok(world)


def test_automatic_invoicing_after_five_days_happens_once(world):
    st = _short(world)
    before = _counts(world)
    # Not yet due: nothing happens.
    assert stocktakes.auto_invoice_due(world.db) == 0
    world.db.commit()
    later = datetime.fromisoformat(st["confirm_due_at"]) + timedelta(minutes=1)
    assert stocktakes.auto_invoice_due(world.db, later) == 1
    world.db.commit()
    assert _counts(world) == (before[0] + 1, before[1] + 1, before[2] + 1)   # a sale, an invoice record, a replacement
    done = world.api(world.manager).get(f"/stocktakes/{st['id']}").json()
    assert done["status"] == "APPROVED" and done["approved_by"] is None
    assert done["confirmed_on_behalf_reason"] == "Automatically invoiced: not found within 5 days"
    sale = world.api(world.manager).get(f"/sales/{done['sale_id']}").json()
    assert sale["source"] == "STOCKTAKE" and sale["lines"][0]["quantity"] == 2 and sale["recorded_by"] is None
    assert world.api(world.manager).get(f"/invoices/{done['invoice_id']}").json()["status"] == "DRAFT"
    for user in (world.user_a, world.rep, world.manager):
        titles = [n["title"] for n in world.api(user).get("/notifications").json()]
        assert f"Stock check {st['number']}: tyres invoiced" in titles
    audit = world.api(world.manager).get("/audit-events", params={"entity_type": "stocktake", "entity_id": st["id"]}).json()
    assert any(a["summary"].startswith("Automatically invoiced: not found within 5 days") for a in audit)
    # Running again (bell or cron) creates nothing new.
    assert stocktakes.auto_invoice_due(world.db, later + timedelta(days=1)) == 0
    world.db.commit()
    world.api(world.user_a).get("/notifications/unread-count")
    assert _counts(world) == (before[0] + 1, before[1] + 1, before[2] + 1)
    assert world.bal(world.loc_a, world.p1).on_hand == 3 and world.bal(world.loc_a, world.p1).blocked == 0
    _ledger_ok(world)


def test_the_cron_endpoint_needs_the_secret(world, monkeypatch):
    world.api(world.manager).get("/stocktakes/auto-invoice/cron", expected=403)
    monkeypatch.setattr(get_settings(), "cron_secret", "s3cret")
    assert world.client.get("/api/stocktakes/auto-invoice/cron",
                            headers={"Authorization": "Bearer nope"}).status_code == 403
    res = world.client.get("/api/stocktakes/auto-invoice/cron", headers={"Authorization": "Bearer s3cret"})
    assert res.status_code == 200 and res.json() == {"invoiced": 0, "reminded": 0}


def test_contacts_come_back_with_phone_numbers(world):
    st = _short(world)
    world.api(world.manager).patch(f"/users/{world.warehouse_op.id}", {"phone": "09 555 0101"})
    people = world.api(world.user_a).get(f"/stocktakes/{st['id']}/contacts").json()
    by_role = {(p["role"], p["name"]): p for p in people}
    assert by_role[("Warehouse Manager", "Wes Warehouse")]["phone"] == "09 555 0101"
    assert ("Relationship Manager", "Morgan Manager") in by_role
    assert by_role[("Your sales rep", "Riley Rep")]["email"] == "rep@example.com"
    world.api(world.user_b).get(f"/stocktakes/{st['id']}/contacts", expected=404)
