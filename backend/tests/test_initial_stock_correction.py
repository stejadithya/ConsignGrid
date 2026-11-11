"""Correcting a dealer's wrongly entered initial stock (UAT): Relationship Manager and Administrator only.

The original entry is never changed; a correction sits next to it in the ledger, the change history and the
reports, and the stock still reconciles.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import select, update

from app.core.permissions import Role
from app.modules.audit.models import AuditEvent
from app.modules.inventory.models import InventoryEntry, InventoryTransaction, TxnType
from app.modules.stock_requests.models import Notification
from tests.factories import make_user

pytestmark = pytest.mark.usefixtures("ledger_balanced")


def initial_stock(world, lines, location=None):
    loc = location or world.loc_a
    return world.api(world.manager).post(f"/resellers/{loc.reseller_id}/initial-stock", {
        "location_id": loc.id, "lines": [{"product_id": p.id, "quantity": q} for p, q in lines]}).json()


def entry(world, user=None, reseller=None):
    [e] = world.api(user or world.manager).get(f"/resellers/{(reseller or world.reseller_a).id}/initial-stock/entries").json()
    return e


def correct(world, e, lines, reason="Typed 12 instead of 2 while serving a customer", user=None, expected=201,
            reseller=None):
    return world.api(user or world.manager).post(
        f"/resellers/{(reseller or world.reseller_a).id}/initial-stock/{e['transaction_id']}/corrections",
        {"lines": [{"product_id": p.id, "quantity": q} for p, q in lines], "reason": reason}, expected=expected).json()


def test_rm_corrects_the_entry_and_the_original_is_kept(world):
    db = world.db
    fm = make_user(db, Role.FINANCE_MANAGER, "fm@example.com")
    root = make_user(db, Role.ADMINISTRATOR, "root@example.com")
    db.commit()
    posted = initial_stock(world, [(world.p1, 12), (world.p2, 4)])
    e = entry(world)
    assert (e["transaction_number"], e["can_correct"]) == (posted["transaction_number"], True)

    c = correct(world, e, [(world.p1, 2), (world.p2, 0), (world.p3, 3)])
    assert [(x["sku"], x["before"], x["after"]) for x in c["changes"]] == \
        [("TYR-001", 12, 2), ("TYR-002", 4, 0), ("TYR-003", 0, 3)]
    assert c["corrected_by"] == "Morgan Manager"

    # Stock now matches the corrected figures.
    assert [world.bal(world.loc_a, p).on_hand for p in (world.p1, world.p2, world.p3)] == [2, 0, 3]
    # The original entry is untouched; the correction points at it.
    original = db.execute(select(InventoryTransaction).where(InventoryTransaction.id == e["transaction_id"])).scalar_one()
    assert original.txn_type == TxnType.OPENING_BALANCE
    at_shop = select(InventoryEntry.quantity).where(InventoryEntry.transaction_id == original.id,
                                                    InventoryEntry.location_id == world.loc_a.id)
    assert sorted(db.execute(at_shop).scalars()) == [4, 12]
    fix = db.get(InventoryTransaction, c["transaction_id"])
    assert (fix.txn_type, fix.reverses_transaction_id, fix.reason) == \
        (TxnType.INITIAL_STOCK_CORRECTION, original.id, "Typed 12 instead of 2 while serving a customer")

    # The entry shows what was recorded and what it is now, with the correction beside it.
    e = entry(world)
    assert [(ln["sku"], ln["recorded"], ln["current"]) for ln in e["lines"]] == \
        [("TYR-001", 12, 2), ("TYR-002", 4, 0), ("TYR-003", 0, 3)]
    assert [x["transaction_number"] for x in e["corrections"]] == [c["transaction_number"]]

    # Change history: who, before → after and why.
    ev = db.execute(select(AuditEvent).where(AuditEvent.action == "inventory.initial_stock_correct")).scalar_one()
    assert ev.actor_user_id == world.manager.id and ev.reseller_id == world.reseller_a.id
    assert "TYR-001 12 → 2" in ev.summary and "Typed 12 instead of 2" in ev.summary
    assert ev.details["corrects_transaction"] == posted["transaction_number"]

    # Administrators and the Finance Manager are told; the RM who did it is not.
    told = set(db.execute(select(Notification.user_id).where(Notification.title.like("Initial stock corrected%"))).scalars())
    assert {fm.id, root.id} <= told and world.manager.id not in told

    # Dealer history shows the corrected stock with the first figures alongside.
    h = world.api(world.warehouse_op).get(f"/resellers/{world.reseller_a.id}/history-summary").json()
    assert [(ln["sku"], ln["quantity"], ln["recorded"]) for ln in h["onboarding_stock"]] == \
        [("TYR-001", 2, 12), ("TYR-002", 0, 4), ("TYR-003", 3, 0)]
    assert h["corrections"] == 1

    # The Stock corrections report lists one row per tyre changed.
    rep = world.api(fm).get("/reports/stock-corrections").json()
    assert rep["corrections"] == 1
    assert sorted((r["sku"], r["before"], r["after"], r["change"]) for r in rep["rows"]) == \
        [("TYR-001", 12, 2, -10), ("TYR-002", 4, 0, -4), ("TYR-003", 0, 3, 3)]
    assert {r["corrected_by"] for r in rep["rows"]} == {"Morgan Manager"}
    assert {r["reason"] for r in rep["rows"]} == {"Typed 12 instead of 2 while serving a customer"}

    # Where did this tyre come from: the tyre added by the correction says so.
    prov = world.api(world.manager).get(f"/inventory/provenance?location_id={world.loc_a.id}&product_id={world.p3.id}")
    assert "initial stock by a correction, recorded by Morgan Manager" in prov.text


def test_sold_reserved_or_blocked_tyres_cannot_be_corrected_away(world):
    initial_stock(world, [(world.p1, 5)])
    world.api(world.rep).post("/sales", {
        "location_id": world.loc_a.id, "sale_date": date.today().isoformat(), "source": "RESELLER_REPORT",
        "source_reference": "Phone call", "lines": [{"product_id": world.p1.id, "quantity": 3}]})
    e = entry(world)
    assert e["lines"][0]["free_now"] == 2
    err = correct(world, e, [(world.p1, 1)], expected=422)
    assert "only 2 of the 5 are still free" in err["detail"]
    correct(world, e, [(world.p1, 3)])
    assert world.bal(world.loc_a, world.p1).on_hand == 0


def test_locked_after_the_first_stock_check_or_after_30_days(world):
    initial_stock(world, [(world.p1, 4)])
    # 31 days later: locked.
    e = entry(world)
    world.db.execute(update(InventoryTransaction).where(InventoryTransaction.id == e["transaction_id"])
                     .values(occurred_at=InventoryTransaction.occurred_at - timedelta(days=31)))
    world.db.commit()
    e = entry(world)
    assert e["can_correct"] is False and "30 days" in e["locked_reason"]
    correct(world, e, [(world.p1, 1)], expected=422)

    # A stock check at the shop locks it too.
    initial_stock(world, [(world.p2, 2)], location=world.loc_b)
    st = world.api(world.rep).post("/stocktakes", {"location_id": world.loc_b.id, "count_date": date.today().isoformat(),
                                                   "counts": [{"product_id": world.p2.id, "counted_qty": 2}]}).json()
    assert entry(world, reseller=world.reseller_b)["can_correct"] is True      # a draft count does not lock it
    world.api(world.rep).post(f"/stocktakes/{st['id']}/submit")
    e = entry(world, reseller=world.reseller_b)
    assert e["can_correct"] is False and "stock check" in e["locked_reason"]
    correct(world, e, [(world.p2, 1)], reseller=world.reseller_b, expected=422)


def test_only_the_relationship_manager_and_administrator(world):
    root = make_user(world.db, Role.ADMINISTRATOR, "root@example.com")
    fm = make_user(world.db, Role.FINANCE_MANAGER, "fm@example.com")
    world.db.commit()
    initial_stock(world, [(world.p1, 6)])
    e = entry(world)
    for user in (world.warehouse_op, world.rep, fm, world.user_a):
        world.api(user).get(f"/resellers/{world.reseller_a.id}/initial-stock/entries", expected=403)
        correct(world, e, [(world.p1, 5)], user=user, expected=403)
    correct(world, e, [(world.p1, 5)], user=root)
    # Another dealer's entry under this dealer's address is not found.
    initial_stock(world, [(world.p2, 2)], location=world.loc_b)
    other = entry(world, reseller=world.reseller_b)
    correct(world, other, [(world.p2, 1)], expected=404)
    # Dealers never see the report.
    world.api(world.user_a).get("/reports/stock-corrections", expected=403)


def test_reason_is_required_and_something_must_change(world):
    initial_stock(world, [(world.p1, 6)])
    e = entry(world)
    correct(world, e, [(world.p1, 5)], reason="oops", expected=422)
    err = correct(world, e, [(world.p1, 6)], expected=422)
    assert "Nothing to change" in err["detail"]
    correct(world, e, [(world.p1, 5), (world.p1, 4)], expected=422)
