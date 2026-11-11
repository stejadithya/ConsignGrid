"""Acceptance tests for the three business scenarios (master instructions §9, tests 1–4, 6, 7)."""

from datetime import date

from sqlalchemy import func, select

from app.modules.inventory.service import reconcile, unbalanced_transactions
from app.modules.invoicing.models import InvoiceLine
from app.modules.replenishment.models import ReplenishmentRequest
from app.modules.sales.models import ConsignmentSaleLine
from tests.factories import HANDOVER, set_stock, set_target

TODAY = date.today().isoformat()


def _sale(api, location, product, qty, expected=201):
    return api.post("/sales", {"location_id": location.id, "sale_date": TODAY, "source": "RESELLER_REPORT",
                               "source_reference": "Phone call", "lines": [{"product_id": product.id, "quantity": qty}]},
                    expected=expected)


def _ledger_ok(db):
    assert reconcile(db) == []
    assert unbalanced_transactions(db) == []


def _sale_line_count(db):
    return db.execute(select(func.count()).select_from(ConsignmentSaleLine)).scalar_one()


# ---------------------------------------------------------------------------
# TEST 1 — Standard sale and replenishment
# ---------------------------------------------------------------------------


def test_1_standard_sale_and_replenishment(world):
    db, rep, wh = world.db, world.api(world.rep), world.api(world.warehouse_op)
    set_stock(db, world.warehouse, world.p1, 100)
    set_stock(db, world.loc_a, world.p1, 20)
    set_target(db, world.loc_a, world.p1, 20)
    db.commit()

    sale = _sale(rep, world.loc_a, world.p1, 8).json()
    # On-hand decreases by 8 on sale; one chargeable sale line exists.
    assert world.bal(world.loc_a, world.p1).on_hand == 12
    assert len(sale["lines"]) == 1 and sale["lines"][0]["chargeable_qty"] == 8
    assert sale["lines"][0]["invoice_status"] == "UNINVOICED"
    assert sale["lines"][0]["unit_price"] == "180.00" and sale["lines"][0]["tax_code"] == "STD"

    # Replenishment demand of 8 (target 20 − 12), linked to the sale, allocated from warehouse.
    [link] = sale["lines"][0]["replenishment"]
    req = rep.get(f"/replenishment/requests/{link['id']}").json()
    assert (req["reason"], req["qty_required"], req["qty_allocated"], req["qty_awaiting_supply"]) == ("SALE", 8, 8, 0)
    assert req["origin_number"] == sale["number"] and req["status"] == "ALLOCATED"
    b = world.bal(world.warehouse, world.p1)
    assert (b.on_hand, b.reserved, b.available) == (100, 8, 92)

    # Dispatch → in transit.
    delivery = wh.post("/replenishment/deliveries", {"to_location_id": world.loc_a.id,
                                                     "lines": [{"request_id": req["id"]}]}, expected=201).json()
    assert delivery["status"] == "IN_TRANSIT" and delivery["lines"][0]["qty_dispatched"] == 8
    b = world.bal(world.warehouse, world.p1)
    assert (b.on_hand, b.reserved) == (92, 0)
    assert rep.get(f"/replenishment/requests/{req['id']}").json()["status"] == "IN_TRANSIT"
    assert world.bal(world.loc_a, world.p1).on_hand == 12  # not counted twice while in transit

    # Confirm receipt → reseller back to 20; request fulfilled.
    sale_lines_before = _sale_line_count(db)
    rep.post(f"/replenishment/deliveries/{delivery['id']}/receive", {**HANDOVER, "lines": []})
    assert world.bal(world.loc_a, world.p1).on_hand == 20
    req = rep.get(f"/replenishment/requests/{req['id']}").json()
    assert (req["status"], req["qty_delivered"], req["qty_outstanding"]) == ("FULFILLED", 8, 0)

    # Replacement delivery created no new chargeable sale and no invoice line.
    assert _sale_line_count(db) == sale_lines_before == 1
    assert db.execute(select(func.count()).select_from(InvoiceLine)).scalar_one() == 0
    _ledger_ok(db)


def test_replenishment_never_exceeds_target_or_duplicates_demand(world):
    db, rep = world.db, world.api(world.rep)
    set_stock(db, world.loc_a, world.p1, 25)   # 5 above target
    set_target(db, world.loc_a, world.p1, 20)
    db.commit()
    s1 = _sale(rep, world.loc_a, world.p1, 8).json()   # 25 → 17: shortfall 3 only
    assert s1["lines"][0]["replenishment"][0]["qty_required"] == 3
    s2 = _sale(rep, world.loc_a, world.p1, 2).json()   # 17 → 15; covered = 15 + 3 = 18 → shortfall 2
    assert s2["lines"][0]["replenishment"][0]["qty_required"] == 2
    # Target shortfall generation finds nothing more to do: all covered by open demand.
    mgr = world.api(world.manager)
    assert mgr.post("/replenishment/generate-shortfalls", {"location_id": world.loc_a.id}).json() == []
    # A manual request above the shortfall needs override permission.
    rep.post("/replenishment/requests", {"location_id": world.loc_a.id, "product_id": world.p1.id, "quantity": 1,
                                         "reason": "Extra"}, expected=422)
    mgr.post("/replenishment/requests", {"location_id": world.loc_a.id, "product_id": world.p1.id, "quantity": 1,
                                         "reason": "Promotion stock"}, expected=201)


def test_sale_without_target_replaces_sold_qty_and_disabled_auto_replenish_raises_none(world):
    """P-017: every sale replaces the same tyre one for one unless auto-replenish is switched off for it."""
    db, rep = world.db, world.api(world.rep)
    set_stock(db, world.loc_a, world.p1, 10)
    set_stock(db, world.loc_b, world.p1, 10)
    set_target(db, world.loc_b, world.p1, 10, auto=False)
    db.commit()
    replacement = _sale(rep, world.loc_a, world.p1, 2).json()["lines"][0]["replenishment"]
    assert [r["qty_required"] for r in replacement] == [2]
    assert _sale(rep, world.loc_b, world.p1, 2).json()["lines"][0]["replenishment"] == []


def test_cannot_sell_reserved_blocked_or_missing_stock(world):
    db, rep = world.db, world.api(world.rep)
    set_stock(db, world.loc_a, world.p1, 3)
    db.commit()
    world.api(world.warehouse_op).post("/inventory/block", {"location_id": world.loc_a.id, "product_id": world.p1.id,
                                                            "quantity": 1, "reason": "Damaged"})
    r = _sale(rep, world.loc_a, world.p1, 3, expected=409)
    assert r.json()["code"] == "insufficient_stock"
    assert world.bal(world.loc_a, world.p1).on_hand == 3
    assert _sale_line_count(db) == 0  # the whole sale rolled back


# ---------------------------------------------------------------------------
# TEST 2 — Warehouse stockout
# ---------------------------------------------------------------------------


def test_2_warehouse_stockout_creates_backorder_until_delivered(world):
    db, rep, wh, mgr = world.db, world.api(world.rep), world.api(world.warehouse_op), world.api(world.manager)
    set_stock(db, world.loc_b, world.p2, 10)
    set_target(db, world.loc_b, world.p2, 10)
    db.commit()

    sale = _sale(rep, world.loc_b, world.p2, 4).json()
    assert world.bal(world.loc_b, world.p2).on_hand == 6
    assert world.bal(world.loc_b, world.p2).available == 6
    line = sale["lines"][0]
    assert line["invoice_status"] == "UNINVOICED" and line["chargeable_qty"] == 4  # invoiceable despite stockout

    [link] = line["replenishment"]
    backorders = rep.get("/replenishment/requests", params={"backorders_only": True}).json()
    assert [(b["id"], b["qty_awaiting_supply"], b["reseller_id"], b["origin_number"]) for b in backorders] == \
        [(link["id"], 4, world.reseller_b.id, sale["number"])]

    # Purchase order: incoming is not stock and does not close the backorder.
    po = world.api(world.warehouse_op).post("/purchasing/purchase-orders", {
        "supplier_name": "Bridgestone Wholesale", "warehouse_location_id": world.warehouse.id,
        "expected_date": "2026-12-01", "lines": [{"product_id": world.p2.id, "qty_ordered": 20}]}).json()
    mgr.post(f"/replenishment/requests/{link['id']}/planning",
             {"reason": "Supplier ETA", "purchase_order_line_id": po["lines"][0]["id"]})
    req = rep.get(f"/replenishment/requests/{link['id']}").json()
    assert req["expected_date"] == "2026-12-01" and req["status"] == "OPEN"
    assert world.bal(world.warehouse, world.p2).on_hand == 0
    assert mgr.get("/purchasing/incoming").json()[0]["incoming_qty"] == 20

    # Goods receipt: stock arrives but the backorder is NOT closed or auto-allocated.
    receipt = wh.post("/purchasing/receipts", {"warehouse_location_id": world.warehouse.id,
                                               "purchase_order_id": po["id"],
                                               "lines": [{"product_id": world.p2.id, "qty_received": 20}]}).json()
    assert receipt["open_backorders_for_received_skus"] == 1
    req = rep.get(f"/replenishment/requests/{link['id']}").json()
    assert (req["status"], req["qty_awaiting_supply"]) == ("OPEN", 4)

    # Proposal → confirm → dispatch → receive.
    proposal = mgr.get("/replenishment/allocation-proposal").json()
    assert [(p["request_id"], p["proposed_qty"]) for p in proposal] == [(link["id"], 4)]
    mgr.post("/replenishment/allocation-proposal/confirm", {"lines": [{"request_id": link["id"], "quantity": 4}]})
    d = wh.post("/replenishment/deliveries", {"to_location_id": world.loc_b.id,
                                              "lines": [{"request_id": link["id"]}]}).json()
    assert rep.get(f"/replenishment/requests/{link['id']}").json()["status"] == "IN_TRANSIT"  # still not closed
    rep.post(f"/replenishment/deliveries/{d['id']}/receive", HANDOVER)
    req = rep.get(f"/replenishment/requests/{link['id']}").json()
    assert req["status"] == "FULFILLED"
    assert world.bal(world.loc_b, world.p2).on_hand == 10
    assert world.bal(world.warehouse, world.p2).on_hand == 16
    _ledger_ok(db)


# ---------------------------------------------------------------------------
# TEST 3 — Inter-reseller transfer
# ---------------------------------------------------------------------------


def test_3_inter_reseller_transfer(world):
    db, rep, mgr, wh = world.db, world.api(world.rep), world.api(world.manager), world.api(world.warehouse_op)
    set_stock(db, world.loc_a, world.p3, 6)
    set_target(db, world.loc_a, world.p3, 6)
    db.commit()
    total_before = world.bal(world.loc_a, world.p3).on_hand + world.bal(world.loc_b, world.p3).on_hand

    t = rep.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p3.id,
                                "quantity": 2, "reason": "Customer needs a matching pair today",
                                "urgency": "URGENT"}, expected=201).json()
    assert t["status"] == "REQUESTED"

    src = rep.get("/transfers/sources", params={"product_id": world.p3.id, "exclude_location_id": world.loc_b.id,
                                                "quantity": 2}).json()
    assert src["warehouse_available"] == 0
    assert [(s["location_code"], s["available"], s["eligible"]) for s in src["sources"]] == [("RA-MAIN", 6, True)]

    rep.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_a.id}, expected=403)  # rep cannot approve
    t = mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_a.id,
                                                   "approval_notes": "Approved by phone"}).json()
    assert t["status"] == "APPROVED" and t["approved_by"] == "Morgan Manager"
    b = world.bal(world.loc_a, world.p3)
    assert (b.on_hand, b.reserved, b.available) == (6, 2, 4)
    assert t["source_request"] is None  # no obligation until stock actually leaves

    t = rep.post(f"/transfers/{t['id']}/collect", {}).json()
    assert t["status"] == "IN_TRANSIT" and t["qty_in_transit"] == 2
    assert world.bal(world.loc_a, world.p3).on_hand == 4
    assert world.bal(world.loc_b, world.p3).on_hand == 0
    src_req = t["source_request"]
    assert (src_req["qty_required"], src_req["qty_awaiting_supply"]) == (2, 2)  # warehouse empty → backorder

    t = rep.post(f"/transfers/{t['id']}/receive", HANDOVER).json()
    assert t["status"] == "COMPLETED"
    assert world.bal(world.loc_b, world.p3).on_hand == 2
    # Total unsold dealership-owned stock across the two resellers is unchanged.
    assert world.bal(world.loc_a, world.p3).on_hand + world.bal(world.loc_b, world.p3).on_hand == total_before

    # Source obligation: reason TRANSFER, linked to the transfer, owed to reseller A.
    req = rep.get(f"/replenishment/requests/{src_req['id']}").json()
    assert (req["reason"], req["reseller_id"], req["transfer_id"], req["status"]) == \
        ("TRANSFER", world.reseller_a.id, t["id"], "OPEN")

    # Nobody was invoiced or charged for the transfer.
    assert _sale_line_count(db) == 0

    # A later sale by B is the chargeable event (B has no target → no replenishment).
    sale = _sale(rep, world.loc_b, world.p3, 1).json()
    assert sale["reseller_id"] == world.reseller_b.id and sale["lines"][0]["chargeable_qty"] == 1
    assert db.execute(select(ConsignmentSaleLine)).scalars().one().sale.reseller_id == world.reseller_b.id

    # New supply replenishes A and resolves its obligation.
    wh.post("/purchasing/receipts", {"warehouse_location_id": world.warehouse.id,
                                     "lines": [{"product_id": world.p3.id, "qty_received": 10}]})
    mgr.post(f"/replenishment/requests/{req['id']}/allocate", {})
    d = wh.post("/replenishment/deliveries", {"to_location_id": world.loc_a.id,
                                              "lines": [{"request_id": req["id"]}]}).json()
    rep.post(f"/replenishment/deliveries/{d['id']}/receive", HANDOVER)
    assert rep.get(f"/replenishment/requests/{req['id']}").json()["status"] == "FULFILLED"
    assert world.bal(world.loc_a, world.p3).on_hand == 6
    _ledger_ok(db)


def test_transfer_excludes_unavailable_stock_and_respects_consent(world):
    db, mgr, rep = world.db, world.api(world.manager), world.api(world.rep)
    set_stock(db, world.loc_a, world.p3, 3)
    set_stock(db, world.loc_c, world.p3, 5)   # RC requires per-transfer consent
    db.commit()
    world.api(world.warehouse_op).post("/inventory/block", {"location_id": world.loc_a.id, "product_id": world.p3.id,
                                                            "quantity": 2, "reason": "Damaged"})
    t = rep.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p3.id,
                                "quantity": 2, "reason": "Urgent"}).json()
    src = {s["location_code"]: s for s in rep.get("/transfers/sources", params={
        "product_id": world.p3.id, "exclude_location_id": world.loc_b.id, "quantity": 2}).json()["sources"]}
    assert src["RA-MAIN"]["available"] == 1 and src["RA-MAIN"]["eligible"] is False
    assert src["RC-MAIN"]["eligible"] is True and src["RC-MAIN"]["transfer_consent"] == "PER_TRANSFER"
    # Cannot take blocked stock from A.
    mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_a.id}, expected=409)
    # C requires a recorded consent reference.
    mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_c.id}, expected=422)
    mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_c.id,
                                               "source_consent_reference": "Email from C owner 29/09"})
    # Same-SKU search is exact: similar-size TYR-001 stock is never offered.
    set_stock(db, world.loc_a, world.p1, 9)
    db.commit()
    codes = [s["location_code"] for s in rep.get("/transfers/sources", params={"product_id": world.p3.id}).json()["sources"]]
    assert "RA-MAIN" in codes and all(c in ("RA-MAIN", "RC-MAIN") for c in codes)


def test_transfer_fulfilling_destination_backorder_prevents_oversupply(world):
    db, rep, mgr = world.db, world.api(world.rep), world.api(world.manager)
    set_stock(db, world.loc_a, world.p2, 6)
    set_stock(db, world.loc_b, world.p2, 10)
    set_target(db, world.loc_b, world.p2, 10)
    db.commit()
    sale = _sale(rep, world.loc_b, world.p2, 4).json()   # backorder 4 for B
    bo_id = sale["lines"][0]["replenishment"][0]["id"]
    t = rep.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p2.id, "quantity": 2,
                                "reason": "Urgent pair", "destination_request_id": bo_id}).json()
    mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_a.id})
    bo = rep.get(f"/replenishment/requests/{bo_id}").json()
    assert (bo["qty_transfer_covered"], bo["qty_awaiting_supply"]) == (2, 2)
    rep.post(f"/transfers/{t['id']}/collect", {})
    rep.post(f"/transfers/{t['id']}/receive", HANDOVER)
    bo = rep.get(f"/replenishment/requests/{bo_id}").json()
    assert (bo["qty_delivered"], bo["qty_transfer_covered"], bo["qty_awaiting_supply"], bo["status"]) == \
        (2, 0, 2, "PARTIALLY_FULFILLED")
    assert world.bal(world.loc_b, world.p2).on_hand == 8   # 6 + 2; remaining 2 still owed
    _ledger_ok(db)


# ---------------------------------------------------------------------------
# TEST 4 — Partial backorder fulfilment
# ---------------------------------------------------------------------------


def test_4_partial_backorder_fulfilment(world):
    db, rep, mgr, wh = world.db, world.api(world.rep), world.api(world.manager), world.api(world.warehouse_op)
    set_stock(db, world.loc_a, world.p1, 5)
    set_target(db, world.loc_a, world.p1, 5)
    db.commit()
    sale = _sale(rep, world.loc_a, world.p1, 5).json()
    rid = sale["lines"][0]["replenishment"][0]["id"]
    assert rep.get(f"/replenishment/requests/{rid}").json()["qty_awaiting_supply"] == 5

    wh.post("/purchasing/receipts", {"warehouse_location_id": world.warehouse.id,
                                     "lines": [{"product_id": world.p1.id, "qty_received": 2}]})
    [prop] = mgr.get("/replenishment/allocation-proposal").json()
    assert prop["proposed_qty"] == 2
    mgr.post("/replenishment/allocation-proposal/confirm", {"lines": [{"request_id": rid, "quantity": 2}]})
    d = wh.post("/replenishment/deliveries", {"to_location_id": world.loc_a.id, "lines": [{"request_id": rid}]}).json()
    rep.post(f"/replenishment/deliveries/{d['id']}/receive", HANDOVER)

    req = rep.get(f"/replenishment/requests/{rid}").json()
    assert (req["qty_delivered"], req["qty_outstanding"], req["qty_awaiting_supply"], req["status"]) == \
        (2, 3, 3, "PARTIALLY_FULFILLED")
    assert len([e for e in req["events"] if e["event_type"] == "DELIVERED"]) == 1
    assert world.bal(world.loc_a, world.p1).on_hand == 2
    assert world.bal(world.warehouse, world.p1).on_hand == 0
    # Totals consistent: stock + outstanding demand = target.
    assert world.bal(world.loc_a, world.p1).on_hand + req["qty_outstanding"] == 5
    backorders = rep.get("/replenishment/requests", params={"backorders_only": True}).json()
    assert [(b["id"], b["qty_awaiting_supply"]) for b in backorders] == [(rid, 3)]
    _ledger_ok(db)


def test_allocation_proposal_follows_priority_then_age(world):
    db, rep, mgr, wh = world.db, world.api(world.rep), world.api(world.manager), world.api(world.warehouse_op)
    for loc in (world.loc_a, world.loc_b):
        set_stock(db, loc, world.p1, 4)
        set_target(db, loc, world.p1, 4)
    db.commit()
    a = _sale(rep, world.loc_a, world.p1, 3).json()["lines"][0]["replenishment"][0]["id"]
    b = _sale(rep, world.loc_b, world.p1, 3).json()["lines"][0]["replenishment"][0]["id"]
    mgr.post(f"/replenishment/requests/{b}/planning", {"priority": "URGENT", "reason": "Fleet customer waiting"})
    wh.post("/purchasing/receipts", {"warehouse_location_id": world.warehouse.id,
                                     "lines": [{"product_id": world.p1.id, "qty_received": 4}]})
    props = mgr.get("/replenishment/allocation-proposal").json()
    assert [(p["request_id"], p["proposed_qty"]) for p in props] == [(b, 3), (a, 1)]
    req_b = rep.get(f"/replenishment/requests/{b}").json()
    assert any(e["event_type"] == "PRIORITY_CHANGED" and "Fleet" in e["reason"] for e in req_b["events"])


def test_backorder_cancellation_requires_permission_and_reason(world):
    db, rep, mgr = world.db, world.api(world.rep), world.api(world.manager)
    set_stock(db, world.loc_a, world.p1, 4)
    set_target(db, world.loc_a, world.p1, 4)
    db.commit()
    rid = _sale(rep, world.loc_a, world.p1, 3).json()["lines"][0]["replenishment"][0]["id"]
    rep.post(f"/replenishment/requests/{rid}/cancel", {"reason": "Not needed"}, expected=403)
    mgr.post(f"/replenishment/requests/{rid}/cancel", {"reason": ""}, expected=422)
    r = mgr.post(f"/replenishment/requests/{rid}/cancel", {"quantity": 1, "reason": "Reseller reduced range"}).json()
    assert (r["qty_cancelled"], r["qty_outstanding"], r["status"]) == (1, 2, "OPEN")
    r = mgr.post(f"/replenishment/requests/{rid}/cancel", {"reason": "Closing range"}).json()
    assert r["status"] == "CANCELLED"


# ---------------------------------------------------------------------------
# TEST 6 — Reseller access isolation
# ---------------------------------------------------------------------------


def test_6_reseller_access_isolation(world):
    db, rep = world.db, world.api(world.rep)
    set_stock(db, world.loc_a, world.p1, 10)
    set_stock(db, world.loc_b, world.p1, 10)
    set_target(db, world.loc_b, world.p1, 10)
    db.commit()
    sale_b = _sale(rep, world.loc_b, world.p1, 2).json()
    rid_b = sale_b["lines"][0]["replenishment"][0]["id"]
    alpha = world.api(world.user_a)

    # Direct access to B's records is rejected without revealing them.
    for url in (f"/sales/{sale_b['id']}", f"/replenishment/requests/{rid_b}", f"/resellers/{world.reseller_b.id}"):
        r = alpha.get(url, expected=404)
        assert "Bravo" not in r.text and str(sale_b["number"]) not in r.text
    # Lists are filtered to A only.
    assert alpha.get("/sales").json() == []
    assert alpha.get("/replenishment/requests").json() == []
    assert alpha.get("/sales", params={"reseller_id": world.reseller_b.id}).json() == []
    txns = alpha.get("/inventory/transactions").json()
    assert all(e["location_id"] != world.loc_b.id for t in txns for e in t["entries"])
    # Reseller users may report their own sales only (never another reseller's location, never manual prices).
    _sale(alpha, world.loc_b, world.p1, 1, expected=404)
    alpha.post("/sales", {"location_id": world.loc_a.id, "sale_date": TODAY, "source": "REP_VISIT",
                          "lines": [{"product_id": world.p1.id, "quantity": 1}]}, expected=422)
    alpha.post("/sales", {"location_id": world.loc_a.id, "sale_date": TODAY, "source": "RESELLER_REPORT",
                          "lines": [{"product_id": world.p1.id, "quantity": 1, "unit_price": "1.00",
                                     "price_override_reason": "cheap"}]}, expected=422)
    own = _sale(alpha, world.loc_a, world.p1, 1).json()
    assert own["reseller_id"] == world.reseller_a.id
    # Other dealership actions remain staff-only.
    alpha.post("/transfers", {"destination_location_id": world.loc_a.id, "product_id": world.p1.id, "quantity": 1,
                              "reason": "x"}, expected=403)
    alpha.get("/transfers/sources", params={"product_id": world.p1.id}, expected=403)
    alpha.get(f"/replenishment/coverage?location_id={world.loc_b.id}&product_id={world.p1.id}", expected=404)


# ---------------------------------------------------------------------------
# TEST 7 — Transfer cancellation and discrepancy
# ---------------------------------------------------------------------------


def test_7a_transfer_cancelled_before_collection(world):
    db, rep, mgr = world.db, world.api(world.rep), world.api(world.manager)
    set_stock(db, world.loc_a, world.p3, 6)
    db.commit()
    t = rep.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p3.id,
                                "quantity": 2, "reason": "Urgent"}).json()
    mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_a.id})
    assert world.bal(world.loc_a, world.p3).reserved == 2
    t = mgr.post(f"/transfers/{t['id']}/cancel", {"reason": "Customer changed mind"}).json()
    assert t["status"] == "CANCELLED"
    b = world.bal(world.loc_a, world.p3)
    assert (b.on_hand, b.reserved, b.available) == (6, 0, 6)
    assert world.bal(world.loc_b, world.p3).on_hand == 0
    # No orphaned replenishment obligation.
    assert db.execute(select(func.count()).select_from(ReplenishmentRequest)).scalar_one() == 0
    _ledger_ok(db)


def test_7b_transfer_short_receipt_and_resolution(world):
    db, rep, mgr = world.db, world.api(world.rep), world.api(world.manager)
    set_stock(db, world.loc_a, world.p3, 6)
    db.commit()
    t = rep.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p3.id,
                                "quantity": 3, "reason": "Urgent"}).json()
    mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_a.id})
    rep.post(f"/transfers/{t['id']}/collect", {})
    t = rep.post(f"/transfers/{t['id']}/receive", {**HANDOVER, "quantity": 2}).json()
    assert (t["status"], t["qty_received"], t["qty_in_transit"]) == ("RECEIVED_WITH_DISCREPANCY", 2, 1)
    # Unresolved quantity remains visible in transit; no duplicate stock.
    from app.modules.customers.models import LocationType
    from app.modules.inventory.service import system_location
    transit = system_location(db, LocationType.TRANSIT)
    assert world.bal(transit, world.p3).on_hand == 1
    assert world.bal(world.loc_a, world.p3).on_hand + world.bal(world.loc_b, world.p3).on_hand == 5
    assert rep.get("/transfers", params={"open_only": True}).json()[0]["qty_in_transit"] == 1

    # The missing tyre turns up at source: return it; the source obligation shrinks by 1.
    t = mgr.post(f"/transfers/{t['id']}/resolve", {"outcome": "RETURN_TO_SOURCE", "quantity": 1,
                                                    "reason": "Left behind at source"}).json()
    assert t["status"] == "COMPLETED" and t["qty_in_transit"] == 0
    assert world.bal(transit, world.p3).on_hand == 0
    assert world.bal(world.loc_a, world.p3).on_hand == 4
    src = rep.get(f"/replenishment/requests/{t['source_request']['id']}").json()
    assert (src["qty_required"], src["qty_cancelled"], src["qty_outstanding"]) == (3, 1, 2)
    _ledger_ok(db)


def test_7c_transfer_reversed_after_collection_and_lost_in_transit(world):
    db, rep, mgr = world.db, world.api(world.rep), world.api(world.manager)
    set_stock(db, world.loc_a, world.p3, 6)
    db.commit()
    # Reversal after collection: explicit return record, obligation fully withdrawn, transfer cancelled.
    t = rep.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p3.id,
                                "quantity": 2, "reason": "Urgent"}).json()
    mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_a.id})
    rep.post(f"/transfers/{t['id']}/collect", {})
    mgr.post(f"/transfers/{t['id']}/cancel", {"reason": "Too late"}, expected=409)
    t = mgr.post(f"/transfers/{t['id']}/resolve", {"outcome": "RETURN_TO_SOURCE", "quantity": 2,
                                                    "reason": "Destination sourced elsewhere"}).json()
    assert t["status"] == "CANCELLED"
    assert world.bal(world.loc_a, world.p3).on_hand == 6
    assert rep.get(f"/replenishment/requests/{t['source_request']['id']}").json()["status"] == "CANCELLED"

    # Lost in transit: requires adjustment permission; source still owed.
    t2 = rep.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p3.id,
                                 "quantity": 1, "reason": "Urgent"}).json()
    mgr.post(f"/transfers/{t2['id']}/approve", {"source_location_id": world.loc_a.id})
    rep.post(f"/transfers/{t2['id']}/collect", {})
    rep.post(f"/transfers/{t2['id']}/resolve", {"outcome": "LOST", "quantity": 1, "reason": "x"}, expected=403)
    t2 = world.api(world.warehouse_op).post(f"/transfers/{t2['id']}/resolve", {"outcome": "LOST", "quantity": 1,
                                                      "reason": "Fell off the ute"}).json()
    assert t2["status"] == "COMPLETED" and t2["qty_lost"] == 1
    assert rep.get(f"/replenishment/requests/{t2['source_request']['id']}").json()["qty_awaiting_supply"] == 1
    _ledger_ok(db)


def test_delivery_short_receipt_and_resolution(world):
    db, rep, mgr, wh = world.db, world.api(world.rep), world.api(world.manager), world.api(world.warehouse_op)
    set_stock(db, world.warehouse, world.p1, 10)
    set_stock(db, world.loc_a, world.p1, 5)
    set_target(db, world.loc_a, world.p1, 5)
    db.commit()
    rid = _sale(rep, world.loc_a, world.p1, 4).json()["lines"][0]["replenishment"][0]["id"]
    d = wh.post("/replenishment/deliveries", {"to_location_id": world.loc_a.id, "lines": [{"request_id": rid}]}).json()
    d = rep.post(f"/replenishment/deliveries/{d['id']}/receive",
                 {**HANDOVER, "lines": [{"line_id": d["lines"][0]["id"], "qty_received": 3}]}).json()
    assert d["status"] == "RECEIVED_WITH_DISCREPANCY" and d["lines"][0]["qty_open"] == 1
    req = rep.get(f"/replenishment/requests/{rid}").json()
    assert (req["qty_delivered"], req["qty_in_transit"], req["status"]) == (3, 1, "IN_TRANSIT")
    d = mgr.post(f"/replenishment/deliveries/{d['id']}/resolve",
                 {"line_id": d["lines"][0]["id"], "outcome": "RETURN_TO_WAREHOUSE", "quantity": 1,
                  "reason": "Left on the truck"}).json()
    assert d["status"] == "CLOSED"
    req = rep.get(f"/replenishment/requests/{rid}").json()
    assert (req["qty_awaiting_supply"], req["status"]) == (1, "PARTIALLY_FULFILLED")
    assert world.bal(world.warehouse, world.p1).on_hand == 7
    _ledger_ok(db)


# ---------------------------------------------------------------------------
# Sales corrections and stocktakes
# ---------------------------------------------------------------------------


def test_sale_reversal_restores_stock_and_withdraws_replacement(world):
    db, rep, fin = world.db, world.api(world.rep), world.api(world.finance)
    set_stock(db, world.loc_a, world.p1, 10)
    set_target(db, world.loc_a, world.p1, 10)
    db.commit()
    sale = _sale(rep, world.loc_a, world.p1, 3).json()
    line_id = sale["lines"][0]["id"]
    rep.post(f"/sales/lines/{line_id}/reverse", {"quantity": 1, "reason": "x"}, expected=403)
    sale = fin.post(f"/sales/lines/{line_id}/reverse", {"quantity": 2, "reason": "Keyed wrong quantity"}).json()
    assert sale["lines"][0]["chargeable_qty"] == 1
    assert world.bal(world.loc_a, world.p1).on_hand == 9  # 10 − 3 sold + 2 reversed
    req = rep.get(f"/replenishment/requests/{sale['lines'][0]['replenishment'][0]['id']}").json()
    assert (req["qty_required"], req["qty_cancelled"], req["qty_outstanding"]) == (3, 2, 1)
    _ledger_ok(db)


def test_stocktake_shortage_is_confirmed_by_reseller_then_invoiced_and_replaced(world):
    """P-018: the rep counts; the reseller confirms each shortage as sold (sale, draft invoice, replacement) or missing."""
    db, rep, mgr, alpha = world.db, world.api(world.rep), world.api(world.manager), world.api(world.user_a)
    set_stock(db, world.loc_a, world.p1, 10)
    set_stock(db, world.loc_a, world.p2, 4)
    set_target(db, world.loc_a, world.p1, 10)
    db.commit()
    st = rep.post("/stocktakes", {"location_id": world.loc_a.id, "count_date": TODAY,
                                  "counts": [{"product_id": world.p1.id, "counted_qty": 6, "counted_damaged_qty": 1}]
                                  }).json()
    st = rep.post(f"/stocktakes/{st['id']}/submit").json()
    assert st["status"] == "AWAITING_RESELLER" and st["total_shortage"] == 8 and st["confirm_due_at"]
    lines = {ln["sku"]: ln for ln in st["lines"]}
    assert lines["TYR-001"]["variance"] == -4
    assert lines["TYR-002"]["counted_qty"] == 0 and lines["TYR-002"]["variance"] == -4  # uncounted SKU added
    # The shortage is held so it cannot be sold or transferred while the reseller decides.
    assert world.bal(world.loc_a, world.p1).blocked == 4 and world.bal(world.loc_a, world.p1).available == 6
    # 1.11 (D3): the dealer has 5 days to find the tyres.
    told = next(n for n in alpha.get("/notifications").json() if n["title"] == f"Stock check {st['number']}: 8 tyre(s) not found")
    assert told["body"].startswith("8 tyre(s) weren't found at today's stock check. You have 5 days to find them.")
    # 1.11 (finding 28): a shortage is never written off as missing; every tyre not found is sold (or re-checked).
    missing = {"lines": [{"line_id": lines["TYR-001"]["id"], "qty_sold": 3, "qty_missing": 1},
                         {"line_id": lines["TYR-002"]["id"], "qty_sold": 0, "qty_missing": 4}]}
    r = alpha.post(f"/stocktakes/{st['id']}/confirm", missing, expected=422).json()
    assert r["detail"] == "In consignment, tyres that aren't found are re-checked or invoiced."
    confirm = {"lines": [{"line_id": lines["TYR-001"]["id"], "qty_sold": 4, "qty_missing": 0},
                         {"line_id": lines["TYR-002"]["id"], "qty_sold": 4, "qty_missing": 0}]}
    # Nothing is assumed: the rep cannot confirm, staff need a reason, and every shortage must add up.
    rep.post(f"/stocktakes/{st['id']}/confirm", confirm, expected=403)
    mgr.post(f"/stocktakes/{st['id']}/confirm", confirm, expected=422)
    world.api(world.user_b).post(f"/stocktakes/{st['id']}/confirm", confirm, expected=404)
    alpha.post(f"/stocktakes/{st['id']}/confirm", {"lines": [
        {"line_id": lines["TYR-001"]["id"], "qty_sold": 1, "qty_missing": 0},
        {"line_id": lines["TYR-002"]["id"], "qty_sold": 4, "qty_missing": 0}]}, expected=422)
    st = alpha.post(f"/stocktakes/{st['id']}/confirm", confirm).json()
    assert st["status"] == "APPROVED" and st["sale_id"] and st["invoice_number"].startswith("INV-")
    b1, b2 = world.bal(world.loc_a, world.p1), world.bal(world.loc_a, world.p2)
    assert (b1.on_hand, b1.blocked, b1.available) == (6, 1, 5)
    assert b2.on_hand == 0 and b2.blocked == 0
    sale = rep.get(f"/sales/{st['sale_id']}").json()
    assert sale["source"] == "STOCKTAKE"
    assert [(ln["sku"], ln["quantity"]) for ln in sale["lines"]] == [("TYR-001", 4), ("TYR-002", 4)]
    # The sold quantity is chargeable and replaced (TYR-001: target 10, on hand 6 → min(4, 4) = 4).
    assert sale["lines"][0]["replenishment"][0]["qty_required"] == 4
    invoice = mgr.get(f"/invoices/{st['invoice_id']}").json()
    assert invoice["status"] == "DRAFT"
    assert [(ln["sku"], ln["quantity"]) for ln in invoice["lines"]] == [("TYR-001", 4), ("TYR-002", 4)]
    assert any(n["title"] == f"Stock check {st['number']} confirmed" for n in mgr.get("/notifications").json())
    _ledger_ok(db)


def test_stocktake_without_shortage_posts_at_submission(world):
    db, rep = world.db, world.api(world.rep)
    set_stock(db, world.loc_a, world.p1, 5)
    db.commit()
    st = rep.post("/stocktakes", {"location_id": world.loc_a.id, "count_date": TODAY,
                                  "counts": [{"product_id": world.p1.id, "counted_qty": 7}]}).json()
    st = rep.post(f"/stocktakes/{st['id']}/submit").json()
    assert st["status"] == "APPROVED" and st["invoice_id"] is None
    assert world.bal(world.loc_a, world.p1).on_hand == 7   # surplus gain posted
    _ledger_ok(db)


def test_unconfirmed_stocktake_sends_repeating_reminders_and_is_listed(world):
    """1.11 (D3): daily reminders during the 5-day find window; at the end the tyres are invoiced automatically."""
    from datetime import UTC, datetime, timedelta

    from app.modules.stocktakes.models import Stocktake

    db, rep, wm, alpha = world.db, world.api(world.rep), world.api(world.warehouse_op), world.api(world.user_a)
    set_stock(db, world.loc_a, world.p1, 5)
    db.commit()
    st = rep.post("/stocktakes", {"location_id": world.loc_a.id, "count_date": TODAY,
                                  "counts": [{"product_id": world.p1.id, "counted_qty": 3}]}).json()
    st = rep.post(f"/stocktakes/{st['id']}/submit").json()
    assert alpha.get("/notifications/unread-count").json()["unread"] == 1   # just counted: no reminder yet
    [pending] = wm.get("/stocktakes/awaiting-confirmation").json()
    assert pending["id"] == st["id"] and pending["overdue"] is False
    assert world.api(world.user_b).get("/stocktakes/awaiting-confirmation").json() == []

    def reminders(user):
        return [n for n in world.api(user).get("/notifications").json() if n["title"].startswith("Reminder:")]

    # A day into the window: one reminder to the dealer and the rep, not repeated within the interval.
    row = db.get(Stocktake, st["id"])
    row.submitted_at -= timedelta(days=1, minutes=1)
    db.commit()
    wm.get("/notifications/unread-count")
    for user in (world.user_a, world.rep):
        assert len(reminders(user)) == 1, user.email
    wm.get("/notifications/unread-count")
    assert len(reminders(world.user_a)) == 1
    [pending] = alpha.get("/stocktakes/awaiting-confirmation").json()
    assert pending["reminder_count"] == 1
    db.expire_all()
    db.get(Stocktake, st["id"]).last_reminded_at = datetime.now(UTC) - timedelta(days=2)
    db.commit()
    alpha.get("/notifications/unread-count")
    assert len(reminders(world.user_a)) == 2
    # The window ends: the tyres are invoiced as sold automatically, with a final notice.
    db.expire_all()
    db.get(Stocktake, st["id"]).confirm_due_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    alpha.get("/notifications/unread-count")
    done = wm.get(f"/stocktakes/{st['id']}").json()
    assert done["status"] == "APPROVED" and done["sale_id"] and done["invoice_id"]
    assert any(n["title"] == f"Stock check {st['number']}: tyres invoiced" for n in alpha.get("/notifications").json())
    assert wm.get("/stocktakes/awaiting-confirmation").json() == []


def test_staff_confirm_on_behalf_and_cancel_releases_hold(world):
    db, rep, mgr = world.db, world.api(world.rep), world.api(world.manager)
    set_stock(db, world.loc_a, world.p1, 5)
    set_stock(db, world.loc_b, world.p1, 5)
    db.commit()
    st = rep.post("/stocktakes", {"location_id": world.loc_a.id, "count_date": TODAY,
                                  "counts": [{"product_id": world.p1.id, "counted_qty": 3}]}).json()
    st = rep.post(f"/stocktakes/{st['id']}/submit").json()
    line = st["lines"][0]
    # 1.11 (finding 28): on the dealer's behalf too, tyres not found are invoiced as sold, never written off.
    st = mgr.post(f"/stocktakes/{st['id']}/confirm", {
        "lines": [{"line_id": line["id"], "qty_sold": 2, "qty_missing": 0}],
        "on_behalf_reason": "Reseller confirmed by phone"}).json()
    assert st["status"] == "APPROVED" and st["confirmed_on_behalf_reason"] == "Reseller confirmed by phone"
    assert st["sale_id"] and st["invoice_id"] and world.bal(world.loc_a, world.p1).on_hand == 3
    other = rep.post("/stocktakes", {"location_id": world.loc_b.id, "count_date": TODAY,
                                     "counts": [{"product_id": world.p1.id, "counted_qty": 4}]}).json()
    rep.post(f"/stocktakes/{other['id']}/submit")
    assert world.bal(world.loc_b, world.p1).blocked == 1
    rep.post(f"/stocktakes/{other['id']}/cancel", {"reason": "Recount needed"})
    assert world.bal(world.loc_b, world.p1).blocked == 0
    _ledger_ok(db)


def test_allocation_positions_show_target_vs_demand(world):
    db, rep = world.db, world.api(world.rep)
    set_stock(db, world.loc_a, world.p1, 10)
    set_target(db, world.loc_a, world.p1, 10)
    db.commit()
    _sale(rep, world.loc_a, world.p1, 4)
    [pos] = rep.get("/allocations/positions", params={"reseller_id": world.reseller_a.id}).json()
    assert (pos["target_qty"], pos["on_hand"], pos["open_replenishment"], pos["remaining_unmet"]) == (10, 6, 4, 0)
    assert world.api(world.user_b).get("/allocations/positions", params={"reseller_id": world.reseller_a.id}).json() == []


def test_reseller_users_do_not_see_transfer_counterparty(world):
    db, rep, mgr = world.db, world.api(world.rep), world.api(world.manager)
    set_stock(db, world.loc_a, world.p3, 6)
    db.commit()
    t = rep.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p3.id,
                                "quantity": 2, "reason": "Urgent"}).json()
    mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_a.id})
    rep.post(f"/transfers/{t['id']}/collect", {})
    as_b = world.api(world.user_b).get(f"/transfers/{t['id']}").json()
    assert as_b["source_reseller_name"] == "Another dealer" and as_b["source_reseller_id"] is None
    assert as_b["source_request"] is None and "Alpha" not in str(as_b)
    as_a = world.api(world.user_a).get("/transfers").json()[0]
    assert as_a["destination_reseller_name"] == "Another dealer" and as_a["source_request"] is not None
    hist = world.api(world.user_a).get(f"/reports/resellers/{world.reseller_a.id}/transactions").json()
    assert "Bravo" not in str(hist)
    # Dealership staff still see both parties.
    assert rep.get(f"/transfers/{t['id']}").json()["source_reseller_name"] == "Alpha Tyres"


def test_on_hold_reseller_sale_does_not_reserve_warehouse_stock(world):
    db, rep, mgr = world.db, world.api(world.rep), world.api(world.manager)
    set_stock(db, world.warehouse, world.p1, 10)
    set_stock(db, world.loc_a, world.p1, 5)
    set_target(db, world.loc_a, world.p1, 5)
    db.commit()
    mgr.post(f"/resellers/{world.reseller_a.id}/status", {"status": "ON_HOLD", "reason": "Credit review"})
    sale = _sale(rep, world.loc_a, world.p1, 2).json()          # the sale is still a chargeable fact
    req = sale["lines"][0]["replenishment"][0]
    assert req["status"] == "OPEN"                                # demand recorded, but no reservation
    assert world.bal(world.warehouse, world.p1).reserved == 0
    assert mgr.get("/replenishment/allocation-proposal").json() == []


def test_reseller_sale_raises_replacement_notifies_staff_and_shows_who_raised_it(world):
    """P-017: a reseller-reported sale queues the same tyre for picking and tells WM, RM and the sales rep."""
    db = world.db
    set_stock(db, world.loc_a, world.p1, 5)
    set_stock(db, world.warehouse, world.p1, 10)
    db.commit()
    alpha = world.api(world.user_a)
    sale = alpha.post("/sales", {"location_id": world.loc_a.id, "sale_date": str(date.today()),
                                 "source": "RESELLER_REPORT", "lines": [{"product_id": world.p1.id, "quantity": 2}]}).json()
    req = sale["lines"][0]["replenishment"][0]
    detail = world.api(world.warehouse_op).get(f"/replenishment/requests/{req['id']}").json()
    assert detail["qty_required"] == 2 and detail["qty_allocated"] == 2   # reserved, so it is on the pick list
    assert detail["raised_by"] == world.user_a.full_name and detail["raised_by_role"] == "RESELLER"
    picks = world.api(world.warehouse_op).get("/replenishment/pick-list").json()
    assert any(p["request_id"] == req["id"] for p in picks)
    for user in (world.warehouse_op, world.manager, world.rep):
        titles = [n["title"] for n in world.api(user).get("/notifications").json()]
        assert "Replacement raised for Alpha Tyres" in titles
    assert world.api(world.user_a).get("/notifications").json() == []
