""""Get this tyre for me": what the warehouse cannot supply is found from another dealer."""

from tests.factories import APPROVAL, set_stock


def _titles(api):
    return [n["title"] for n in api.get("/notifications").json()]


def test_supply_check_says_only_yes_or_no(world):
    set_stock(world.db, world.warehouse, world.p1, 2)
    world.db.commit()
    res = world.api(world.user_a).post("/stock-requests/supply-check", {"lines": [
        {"product_id": world.p1.id, "quantity": 2}, {"product_id": world.p1.id, "quantity": 5},
        {"product_id": world.p2.id, "quantity": 1}]}).json()
    assert res == [{"product_id": world.p1.id, "needs_help": False}, {"product_id": world.p1.id, "needs_help": True},
                   {"product_id": world.p2.id, "needs_help": True}]


def test_shortfall_goes_to_the_warehouse_and_the_rest_to_approval(world):
    set_stock(world.db, world.warehouse, world.p1, 2)
    set_stock(world.db, world.warehouse, world.p2, 3)
    world.db.commit()
    dealer, rm, wm = world.api(world.user_a), world.api(world.manager), world.api(world.warehouse_op)
    sr = dealer.post("/stock-requests", {"location_id": world.loc_a.id, "submit": True, "lines": [
        {"product_id": world.p1.id, "quantity": 5, "find_for_me": True},
        {"product_id": world.p2.id, "quantity": 1}]}, expected=201).json()
    assert sr["status"] == "SUBMITTED"
    l1, l2 = sr["lines"]
    assert (l1["find_for_me"], l1["qty_arranging"], l2["qty_arranging"]) == (True, 3, 0)
    t = wm.get(f"/transfers/{l1['arranging_transfer_id']}").json()
    assert (t["status"], t["quantity"], t["destination_location_id"]) == ("REQUESTED", 3, world.loc_a.id)
    assert l1["arranging_transfer_number"] == t["number"]
    assert any(x.startswith("Please find") for x in _titles(wm))
    assert any(x.startswith("Please find") for x in _titles(rm))

    # The Central Team decides only what the warehouse can supply.
    sr = rm.post(f"/stock-requests/{sr['id']}/review").json()
    def body(q1):
        return {"lines": [{"line_id": l1["id"], "approve_qty": q1}, {"line_id": l2["id"], "approve_qty": 1}],
                "approval": APPROVAL}

    rm.post(f"/stock-requests/{sr['id']}/decision", body(3), expected=422)
    sr = rm.post(f"/stock-requests/{sr['id']}/decision", body(2)).json()
    assert sr["status"] == "APPROVED"
    assert (sr["lines"][0]["qty_approved"], sr["lines"][0]["qty_backordered"]) == (2, 0)


def test_fully_arranged_request_needs_no_approval_and_dealer_hears_when_on_its_way(world):
    set_stock(world.db, world.loc_b, world.p3, 4)   # another dealer holds it; the warehouse has none
    world.db.commit()
    dealer, rm, wm = world.api(world.user_a), world.api(world.manager), world.api(world.warehouse_op)
    sr = dealer.post("/stock-requests", {"location_id": world.loc_a.id, "submit": True, "lines": [
        {"product_id": world.p3.id, "quantity": 2, "find_for_me": True}]}, expected=201).json()
    assert sr["status"] == "APPROVED" and sr["closed_at"]
    assert not any(x.endswith("waiting for approval") for x in _titles(rm))
    assert sr["id"] not in [r["id"] for r in rm.get("/stock-requests", params={"view": "approved"}).json()]

    tid = sr["lines"][0]["arranging_transfer_id"]
    wm.post(f"/transfers/{tid}/approve", {"source_location_id": world.loc_b.id,
                                          "source_consent_reference": "Phoned Bravo 12/10"})
    wm.post(f"/transfers/{tid}/collect", {})
    assert any(x.startswith("Good news") for x in _titles(dealer))
    wm.post(f"/transfers/{tid}/receive", {}, expected=200)
    assert world.bal(world.loc_a, world.p3).on_hand == 2


def test_team_is_told_when_an_arrangement_falls_through(world):
    dealer, rm, wm = world.api(world.user_a), world.api(world.manager), world.api(world.warehouse_op)
    sr = dealer.post("/stock-requests", {"location_id": world.loc_a.id, "submit": True, "lines": [
        {"product_id": world.p3.id, "quantity": 1, "find_for_me": True}]}, expected=201).json()
    wm.post(f"/transfers/{sr['lines'][0]['arranging_transfer_id']}/reject", {"reason": "Nobody holds it"})
    assert any("still waiting" in x for x in _titles(rm))
    assert not any("still waiting" in x for x in _titles(dealer))


def test_without_the_button_nothing_changes(world):
    dealer = world.api(world.user_a)
    sr = dealer.post("/stock-requests", {"location_id": world.loc_a.id, "submit": True, "lines": [
        {"product_id": world.p3.id, "quantity": 1}]}, expected=201).json()
    assert sr["status"] == "SUBMITTED" and sr["lines"][0]["qty_arranging"] == 0
    assert sr["lines"][0]["arranging_transfer_id"] is None
