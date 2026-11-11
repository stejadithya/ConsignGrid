"""Proof of receipt: who may confirm, what a Sales Rep records, drop-off photos, and Check Stock access."""

import base64
from io import BytesIO

from PIL import Image

from app.core.permissions import Role
from tests.factories import HANDOVER, make_user, set_stock


def _photo(size=(640, 480)) -> str:
    buf = BytesIO()
    Image.new("RGB", size, (200, 180, 40)).save(buf, "JPEG", quality=60)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _rep_delivery(world, qty=2):
    set_stock(world.db, world.warehouse, world.p1, 10)
    world.db.commit()
    req = world.api(world.manager).post("/replenishment/requests", {
        "location_id": world.loc_a.id, "product_id": world.p1.id, "quantity": qty, "reason": "Stock"}).json()
    return world.api(world.warehouse_op).post("/replenishment/deliveries", {
        "to_location_id": world.loc_a.id, "lines": [{"request_id": req["id"], "quantity": qty}],
        "shipping_method": "SALES_REP", "carried_by_user_id": world.rep.id}, expected=201).json()


def test_rep_carried_delivery_only_dealer_or_that_rep_confirms(world):
    d = _rep_delivery(world)
    url = f"/replenishment/deliveries/{d['id']}/receive"
    other_rep = make_user(world.db, Role.SALES_REP, "other.rep@example.com")
    world.db.commit()
    world.api(world.warehouse_op).post(url, HANDOVER, expected=403)
    world.api(world.manager).post(url, HANDOVER, expected=403)
    world.api(other_rep).post(url, HANDOVER, expected=403)
    world.api(world.user_b).post(url, {}, expected=404)                  # another dealer
    rep = world.api(world.rep)
    rep.post(url, {}, expected=422)                                      # who received it?
    rep.post(url, {"received_by_name": "Ravi"}, expected=422)            # and a short note
    d = rep.post(url, {**HANDOVER, "received_by_name": "Ravi (owner)", "photos": [_photo()]}).json()
    assert d["status"] == "RECEIVED" and d["received_by_name"] == "Ravi (owner)"
    assert d["receipt_notes"] == HANDOVER["notes"] and len(d["photos"]) == 1
    # The dealer and staff can see the photo; another dealer cannot.
    img = world.api(world.user_a).get(f"/proofs/photos/{d['photos'][0]}")
    assert img.headers["content-type"] == "image/jpeg" and img.content[:3] == b"\xff\xd8\xff"
    world.api(world.warehouse_op).get(f"/proofs/photos/{d['photos'][0]}", expected=200)
    world.api(world.user_b).get(f"/proofs/photos/{d['photos'][0]}", expected=404)
    pdf = world.api(world.user_a).get(f"/replenishment/deliveries/{d['id']}/delivery-note.pdf").content
    assert pdf[:5] == b"%PDF-"


def test_dealer_confirms_without_name_and_courier_deliveries_unchanged(world):
    d = _rep_delivery(world)
    d = world.api(world.user_a).post(f"/replenishment/deliveries/{d['id']}/receive", {}).json()
    assert d["status"] == "RECEIVED" and d["received_by_name"] is None
    req = world.api(world.manager).post("/replenishment/requests", {
        "location_id": world.loc_a.id, "product_id": world.p1.id, "quantity": 1, "reason": "Stock"}).json()
    c = world.api(world.warehouse_op).post("/replenishment/deliveries", {
        "to_location_id": world.loc_a.id, "carrier_reference": "StarTrack",
        "lines": [{"request_id": req["id"], "quantity": 1}]}).json()
    world.api(world.warehouse_op).post(f"/replenishment/deliveries/{c['id']}/receive", {}, expected=200)


def _transfer_in_transit(world, collector):
    set_stock(world.db, world.loc_a, world.p3, 6)
    world.db.commit()
    mgr = world.api(world.manager)
    t = mgr.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p3.id, "quantity": 2,
                                "reason": "Customer waiting"}, expected=201).json()
    mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_a.id,
                                               "source_consent_reference": "Phoned owner"})
    return world.api(collector).post(f"/transfers/{t['id']}/collect", {}).json()


def test_transfer_collected_by_rep_dealer_or_rep_confirms(world):
    t = _transfer_in_transit(world, world.rep)
    assert t["collected_by_sales_rep"] is True
    url = f"/transfers/{t['id']}/receive"
    world.api(world.warehouse_op).post(url, HANDOVER, expected=403)
    world.api(world.user_a).post(url, {}, expected=404)                  # the giving dealer is not the receiver
    t = world.api(world.user_b).post(url, {"photos": [_photo()]}).json()  # the receiving dealer can confirm
    assert t["status"] == "COMPLETED" and len(t["photos"]) == 1
    assert world.bal(world.loc_b, world.p3).on_hand == 2


def test_transfer_collected_by_warehouse_staff_can_still_confirm(world):
    t = _transfer_in_transit(world, world.warehouse_op)
    t = world.api(world.warehouse_op).post(f"/transfers/{t['id']}/receive", {"received_by_name": "Mia"}).json()
    assert t["status"] == "COMPLETED" and t["received_by_name"] == "Mia"


def test_photo_rules(world):
    d = _rep_delivery(world)
    rep = world.api(world.rep)
    rep.post(f"/replenishment/deliveries/{d['id']}/receive", {**HANDOVER, "photos": ["data:text/plain;base64,aGk="]},
             expected=422)
    rep.post(f"/replenishment/deliveries/{d['id']}/receive", {**HANDOVER, "photos": [_photo()] * 4}, expected=422)
    rep.post(f"/replenishment/deliveries/{d['id']}/receive", {**HANDOVER, "photos": [_photo()] * 3}, expected=200)
    world.api(world.user_a).post(f"/proofs/delivery/{d['id']}/photos", {"data_url": _photo()}, expected=422)  # max 3


def test_check_stock_for_staff_and_sales_reps_not_dealers(world):
    set_stock(world.db, world.loc_a, world.p2, 4)
    world.db.commit()
    for u in (world.rep, world.manager, world.warehouse_op):
        res = world.api(u).get("/transfers/sources", params={"product_id": world.p2.id}).json()
        assert [(s["location_code"], s["on_hand"]) for s in res["sources"]] == [(world.loc_a.code, 4)]
    world.api(world.user_a).get("/transfers/sources", params={"product_id": world.p2.id}, expected=403)
