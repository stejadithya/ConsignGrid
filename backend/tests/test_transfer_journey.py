"""Stock transfer journey (UAT round 2, journey 5).

A Sales Rep orders 7; the warehouse has 4. The Warehouse Manager approves the 4 and arranges the other 3 from
another dealer in the same step. The transfer is approved from the dealer who holds them, and the pick-up is
arranged either direct to the receiving dealer or via the warehouse, where the tyres are received and checked
before the rep delivers them. Each hand-over keeps its evidence.
"""

import pytest
from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from tests.factories import APPROVAL, HANDOVER, set_stock

pytestmark = pytest.mark.usefixtures("ledger_balanced")


def _order_7_with_4_in_the_warehouse(world):
    db = world.db
    set_stock(db, world.warehouse, world.p2, 4)
    set_stock(db, world.loc_a, world.p2, 5)            # Alpha holds the tyre
    db.commit()
    sr = world.api(world.rep).post("/stock-requests", {"location_id": world.loc_b.id, "submit": True,
                                                       "lines": [{"product_id": world.p2.id, "quantity": 7}]}).json()
    wm = world.api(world.warehouse_op)
    done = wm.post(f"/stock-requests/{sr['id']}/decision", {
        "lines": [{"line_id": sr["lines"][0]["id"], "approve_qty": 4, "remainder": "TRANSFER"}], "approval": APPROVAL}).json()
    return sr, done


def _titles(world, user):
    return {n["title"]: n["body"] for n in world.api(user).get("/notifications").json()}


def test_approve_4_and_arrange_3_from_another_dealer_in_one_step(world):
    sr, done = _order_7_with_4_in_the_warehouse(world)
    line = done["lines"][0]
    assert (line["qty_approved"], line["qty_backordered"]) == (4, 3)
    assert done["status"] == "PARTIALLY_APPROVED"
    detail = world.api(world.warehouse_op).get(f"/stock-requests/{sr['id']}").json()
    [cover] = detail["lines"][0]["covering_transfers"]
    assert (cover["status"], cover["quantity"]) == ("REQUESTED", 3)
    t = world.api(world.warehouse_op).get(f"/transfers/{cover['id']}").json()
    assert t["destination_request"]["id"] == line["replenishment_request_id"]
    assert t["destination_location_id"] == world.loc_b.id
    # The dealer doesn't see which dealer it comes from.
    assert world.api(world.user_b).get(f"/stock-requests/{sr['id']}").json()["lines"][0]["covering_transfers"] == []


def test_via_the_warehouse_collection_check_and_delivery_with_evidence(world):
    sr, done = _order_7_with_4_in_the_warehouse(world)
    detail = world.api(world.warehouse_op).get(f"/stock-requests/{sr['id']}").json()
    tid = detail["lines"][0]["covering_transfers"][0]["id"]
    wm, rep, url = world.api(world.warehouse_op), world.api(world.rep), f"/transfers/{tid}"
    t = wm.post(f"{url}/approve", {"source_location_id": world.loc_a.id, "source_consent_reference": "Phoned Alpha",
                                   "shipping": {"shipping_method": "SALES_REP", "carried_by_user_id": world.rep.id,
                                                "route": "VIA_WAREHOUSE"}}).json()
    assert (t["status"], t["route"]) == ("APPROVED", "VIA_WAREHOUSE")
    body = _titles(world, world.rep)[f"Please collect {t['number']} (3 × {world.p2.tyre_label})"]
    assert "bring the tyres to the warehouse to be checked, then deliver to Bravo Auto" in body

    # Collection at Alpha: who handed them over is required.
    rep.post(f"{url}/collect", {}, expected=422)
    t = rep.post(f"{url}/collect", {"collected_from_name": "Sam at Alpha"}).json()
    assert t["status"] == "IN_TRANSIT"

    # Not delivered until the warehouse has received and checked them.
    r = rep.post(f"{url}/receive", HANDOVER, expected=409)
    assert r.json()["code"] == "awaiting_warehouse_check"
    rep.post(f"{url}/warehouse-receipt", {"notes": "3 arrived, good condition"}, expected=403)   # not the rep
    wm.post(f"{url}/warehouse-receipt", {"notes": "ok"}, expected=422)                           # say what was seen
    t = wm.post(f"{url}/warehouse-receipt", {"notes": "3 arrived, good condition"}).json()
    assert t["warehouse_received_by"] == "Wes Warehouse" and t["warehouse_check_notes"] == "3 arrived, good condition"
    assert t["status"] == "IN_TRANSIT"                                                           # still on its way
    wm.post(f"{url}/warehouse-receipt", {"notes": "again"}, expected=409)
    assert f"{t['number']} is checked: please deliver it" in _titles(world, world.rep)

    # The rep delivers to Bravo with the hand-over details.
    rep.post(f"{url}/receive", {}, expected=422)
    t = rep.post(f"{url}/receive", HANDOVER).json()
    assert t["status"] == "COMPLETED" and t["received_by_name"] == "Shop owner"
    assert world.bal(world.loc_b, world.p2).on_hand == 3
    assert world.bal(world.loc_a, world.p2).on_hand == 2
    # Alpha's replacement was raised; Bravo's backorder for the 3 is filled; the dealer never sees the check notes.
    assert t["source_request"] is not None
    line = world.api(world.warehouse_op).get(f"/stock-requests/{sr['id']}").json()["lines"][0]
    assert line["qty_backorder_open"] == 0 and line["qty_delivered"] == 3
    assert world.api(world.user_b).get(url).json()["warehouse_check_notes"] is None
    actions = world.db.execute(select(AuditEvent.action).where(AuditEvent.entity_id == tid,
                                                               AuditEvent.entity_type == "transfer")).scalars().all()
    assert {"transfer.approve", "transfer.collect", "transfer.warehouse_receive", "transfer.receive"} <= set(actions)


def test_direct_route_needs_no_warehouse_step(world):
    sr, _ = _order_7_with_4_in_the_warehouse(world)
    detail = world.api(world.warehouse_op).get(f"/stock-requests/{sr['id']}").json()
    url = f"/transfers/{detail['lines'][0]['covering_transfers'][0]['id']}"
    wm, rep = world.api(world.warehouse_op), world.api(world.rep)
    t = wm.post(f"{url}/approve", {"source_location_id": world.loc_a.id, "source_consent_reference": "Phoned Alpha",
                                   "shipping": {"shipping_method": "SALES_REP", "carried_by_user_id": world.rep.id}}).json()
    assert t["route"] == "DIRECT"
    rep.post(f"{url}/collect", {"collected_from_name": "Sam at Alpha"})
    wm.post(f"{url}/warehouse-receipt", {"notes": "3 arrived, good condition"}, expected=422)   # not via the warehouse
    assert rep.post(f"{url}/receive", HANDOVER).json()["status"] == "COMPLETED"


def test_a_stock_request_backorder_can_be_covered_later_from_backorders(world):
    """Backordered first, then covered with a transfer (the Backorders "Cover with a transfer" button)."""
    db = world.db
    set_stock(db, world.loc_a, world.p2, 5)
    db.commit()
    sr = world.api(world.rep).post("/stock-requests", {"location_id": world.loc_b.id, "submit": True,
                                                       "lines": [{"product_id": world.p2.id, "quantity": 2}]}).json()
    wm = world.api(world.warehouse_op)
    done = wm.post(f"/stock-requests/{sr['id']}/decision", {
        "lines": [{"line_id": sr["lines"][0]["id"], "approve_qty": 0, "remainder": "BACKORDER"}], "approval": APPROVAL}).json()
    req_id = done["lines"][0]["replenishment_request_id"]
    t = wm.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p2.id, "quantity": 2,
                               "reason": "Covers backorder", "destination_request_id": req_id}, expected=201).json()
    wm.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_a.id, "source_consent_reference": "Phoned"})
    rep = world.api(world.rep)
    rep.post(f"/transfers/{t['id']}/collect", {})
    rep.post(f"/transfers/{t['id']}/receive", HANDOVER)
    line = wm.get(f"/stock-requests/{sr['id']}").json()["lines"][0]
    assert line["qty_delivered"] == 2 and line["qty_backorder_open"] == 0
