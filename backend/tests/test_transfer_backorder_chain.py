"""A dealer's backorder covered by a transfer from another dealer: the chain is tagged both ways.

Sale at B with no warehouse stock → backorder at B; transfer from A linked to it → on collection A gets a replacement
(its own backorder). B's request shows the transfer and A's replacement; A's replacement shows the request it filled.
Staff only: dealers never see the other dealer.
"""

from datetime import date

import pytest

from tests.factories import HANDOVER, set_stock, set_target

pytestmark = pytest.mark.usefixtures("ledger_balanced")


def _backorder_at_b(world, qty=2):
    db, rep = world.db, world.api(world.rep)
    set_stock(db, world.loc_a, world.p2, 6)
    set_stock(db, world.loc_b, world.p2, 10)
    set_target(db, world.loc_b, world.p2, 10)
    db.commit()
    sale = rep.post("/sales", {"location_id": world.loc_b.id, "sale_date": date.today().isoformat(), "source": "RESELLER_REPORT",
                               "source_reference": "Phone call", "lines": [{"product_id": world.p2.id, "quantity": qty}]}).json()
    return sale["lines"][0]["replenishment"][0]["id"]


def test_chain_is_tagged_from_approval_to_collection_and_both_sides_see_it(world):
    rep, mgr = world.api(world.rep), world.api(world.manager)
    bo_id = _backorder_at_b(world)
    t = rep.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p2.id, "quantity": 2,
                                "reason": "Covers backorder", "destination_request_id": bo_id}).json()
    mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_a.id})

    # Approved: B's backorder is covered by the transfer; A's replacement comes with the collection.
    bo = mgr.get(f"/replenishment/requests/{bo_id}").json()
    assert bo["qty_transfer_covered"] == 2 and bo["qty_awaiting_supply"] == 0
    [cover] = bo["covered_by_transfers"]
    assert (cover["number"], cover["status"], cover["quantity"]) == (t["number"], "APPROVED", 2)
    assert cover["source_reseller_name"] == "Alpha Tyres"
    assert cover["replacement"] is None
    assert bo["fills_request"] is None

    # Collected: A is owed a replacement (its own backorder, since the warehouse has none), tagged to B's request.
    rep.post(f"/transfers/{t['id']}/collect", {})
    bo = mgr.get(f"/replenishment/requests/{bo_id}").json()
    replacement = bo["covered_by_transfers"][0]["replacement"]
    assert replacement is not None and replacement["reseller_name"] == "Alpha Tyres"
    assert replacement["qty_awaiting_supply"] == 2
    owed = mgr.get(f"/replenishment/requests/{replacement['id']}").json()
    assert owed["reason"] == "TRANSFER" and owed["origin_number"] == t["number"]
    assert owed["fills_request"]["id"] == bo_id and owed["fills_request"]["reseller_name"] == "Bravo Auto"
    assert owed["covered_by_transfers"] == []

    # Delivered to B: B's request is fulfilled; A's replacement stays open until the warehouse supplies it.
    rep.post(f"/transfers/{t['id']}/receive", HANDOVER)
    bo = mgr.get(f"/replenishment/requests/{bo_id}").json()
    assert bo["status"] == "FULFILLED" and bo["covered_by_transfers"][0]["status"] == "COMPLETED"
    assert mgr.get(f"/replenishment/requests/{replacement['id']}").json()["qty_awaiting_supply"] == 2


def test_dealers_never_see_the_other_dealer_in_the_chain(world):
    rep, mgr = world.api(world.rep), world.api(world.manager)
    bo_id = _backorder_at_b(world)
    t = rep.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p2.id, "quantity": 2,
                                "reason": "Covers backorder", "destination_request_id": bo_id}).json()
    mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_a.id})
    rep.post(f"/transfers/{t['id']}/collect", {})
    as_b = world.api(world.user_b).get(f"/replenishment/requests/{bo_id}").json()
    assert as_b["covered_by_transfers"] == [] and as_b["fills_request"] is None
    owed_id = mgr.get(f"/replenishment/requests/{bo_id}").json()["covered_by_transfers"][0]["replacement"]["id"]
    as_a = world.api(world.user_a).get(f"/replenishment/requests/{owed_id}").json()
    assert as_a["fills_request"] is None
    rep.post(f"/transfers/{t['id']}/receive", HANDOVER)


def test_backorder_report_rows_carry_the_location_for_the_cover_action(world):
    bo_id = _backorder_at_b(world)
    rows = world.api(world.manager).get("/reports/backorders").json()["rows"]
    row = next(r for r in rows if r["request_id"] == bo_id)
    assert row["location_id"] == world.loc_b.id and row["location_code"] == world.loc_b.code
