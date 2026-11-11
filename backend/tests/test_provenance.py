"""The ⓘ next to a SKU: where the tyres at a location came from, in plain words."""

from datetime import date

from tests.factories import APPROVAL, set_stock

TODAY = str(date.today())


def _deliver(world, request_ids_qty):
    wm = world.api(world.warehouse_op)
    d = wm.post("/replenishment/deliveries", {"to_location_id": world.loc_a.id, "carrier_reference": "StarTrack",
                                              "lines": [{"request_id": r, "quantity": q} for r, q in request_ids_qty]},
                expected=201).json()
    world.api(world.user_a).post(f"/replenishment/deliveries/{d['id']}/receive", {"lines": []})
    return d


def test_provenance_explains_initial_stock_replacements_and_orders(world):
    set_stock(world.db, world.warehouse, world.p1, 10)
    set_stock(world.db, world.warehouse, world.p2, 10)
    world.db.commit()
    rm, dealer = world.api(world.manager), world.api(world.user_a)
    rm.post(f"/resellers/{world.reseller_a.id}/initial-stock",
            {"location_id": world.loc_a.id, "lines": [{"product_id": world.p1.id, "quantity": 6}]}, expected=201)

    # The dealer sells 2; the automatic replacement is delivered.
    sale = dealer.post("/sales", {"location_id": world.loc_a.id, "sale_date": TODAY,
                                  "lines": [{"product_id": world.p1.id, "quantity": 2}]}, expected=201).json()
    [req] = [r for r in rm.get("/replenishment/requests").json() if r["origin_number"] == sale["number"]]
    d = _deliver(world, [(req["id"], 2)])

    url = f"/inventory/provenance?location_id={world.loc_a.id}&product_id={world.p1.id}"
    mine = dealer.get(url).json()
    assert mine["on_hand"] == 6
    latest, first = mine["arrivals"]
    assert latest["qty"] == 2 and latest["reference"] == d["number"]
    assert latest["reason"] == f"Replacement for your sale {sale['number']}"
    assert first["reason"] == f"Part of your initial stock, recorded by {world.manager.full_name} (Relationship Manager)"
    assert mine["in_stock"] == [{"label": "replacing sales", "qty": 2}, {"label": "initial stock", "qty": 4}]

    staff = rm.get(url).json()
    assert staff["arrivals"][0]["reason"] == f"Replacement for the dealer's sale {sale['number']}"

    # Other dealers cannot look at this location.
    world.api(world.user_b).get(url, expected=404)

    # A brand-new tyre ordered by the RM reads as "Latest stock".
    new = rm.post("/replenishment/requests", {"location_id": world.loc_a.id, "product_id": world.p2.id, "quantity": 3,
                                              "reason": "New line"}, expected=201).json()
    _deliver(world, [(new["id"], 3)])
    p2 = dealer.get(f"/inventory/provenance?location_id={world.loc_a.id}&product_id={world.p2.id}").json()
    assert p2["arrivals"][0]["reason"] == (
        f"Latest stock: a new tyre ordered by {world.manager.full_name} (Relationship Manager) ({new['number']})")
    assert p2["in_stock"] == [{"label": "Latest stock", "qty": 3}]


def test_provenance_for_a_dealer_order_and_empty_history(world):
    set_stock(world.db, world.warehouse, world.p1, 10)
    world.db.commit()
    dealer, rm = world.api(world.user_a), world.api(world.manager)
    set_stock(world.db, world.loc_a, world.p1, 1)
    world.db.commit()
    sr = dealer.post("/stock-requests", {"location_id": world.loc_a.id, "submit": True,
                                         "lines": [{"product_id": world.p1.id, "quantity": 2}]}, expected=201).json()
    sr = rm.post(f"/stock-requests/{sr['id']}/review").json()
    rm.post(f"/stock-requests/{sr['id']}/decision",
            {"lines": [{"line_id": sr["lines"][0]["id"], "approve_qty": 2}], "notes": None, "approval": APPROVAL},
            expected=200)
    [req] = [r for r in rm.get("/replenishment/requests").json() if r["origin_number"] == sr["number"]]
    _deliver(world, [(req["id"], 2)])
    p = dealer.get(f"/inventory/provenance?location_id={world.loc_a.id}&product_id={world.p1.id}").json()
    assert p["arrivals"][0]["reason"] == f"You ordered this ({sr['number']})"
    staff = rm.get(f"/inventory/provenance?location_id={world.loc_a.id}&product_id={world.p1.id}").json()
    assert staff["arrivals"][0]["reason"].startswith(f"Ordered by {world.user_a.full_name} (Dealer)")

    empty = dealer.get(f"/inventory/provenance?location_id={world.loc_a.id}&product_id={world.p3.id}").json()
    assert empty == {"location_id": world.loc_a.id, "product_id": world.p3.id, "on_hand": 0,
                     "arrivals": [], "more": False, "in_stock": []}
