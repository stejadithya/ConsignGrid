"""How a dealer gets their first stock (UAT round 2, journey 3).

A dealer who already held the supplier's stock when added records it as initial stock. A new dealer's stock comes from
the warehouse through a stock request: approval, picking and delivery by the Sales Rep, like any other order.
"""

import pytest
from sqlalchemy import select

from app.modules.customers.models import Location
from app.modules.stock_requests.models import Notification
from tests.factories import make_product, set_stock

pytestmark = pytest.mark.usefixtures("ledger_balanced")


def _create(world, joined_with_stock, name):
    body = {"business_name": name, "contact_name": "Owner", "email": f"{name.split()[0].lower()}@example.com",
            "phone": "09 555 0101", "billing_address": "1 Queen Street, Auckland", "sales_rep_user_id": world.rep.id,
            "locations": [{"name": "Main shop", "address_line1": "1 Queen Street", "city": "Auckland"}],
            "joined_with_stock": joined_with_stock}
    return world.api(world.manager).post("/resellers", body).json()


def _shop(world, reseller):
    return world.db.execute(select(Location).where(Location.reseller_id == reseller["id"])).scalar_one()


def test_a_new_dealer_gets_stock_through_a_stock_request_not_initial_stock(world):
    p = make_product(world.db, "TYR-NEW")
    set_stock(world.db, world.warehouse, p, 10)
    world.db.commit()
    r = _create(world, False, "Roskill Tyres")
    assert r["joined_with_stock"] is False
    shop = _shop(world, r)
    rm = world.api(world.manager)

    # Initial stock (typed or Excel) is refused, with what to do instead.
    err = rm.post(f"/resellers/{r['id']}/initial-stock", {"location_id": shop.id,
                                                          "lines": [{"product_id": p.id, "quantity": 4}]}, expected=422)
    assert "create a stock request" in err.json()["detail"]
    rm.post(f"/resellers/{r['id']}/initial-stock/import", {"content_base64": "AAAA"}, expected=422)
    assert world.bal(shop, p).on_hand == 0

    # The first order goes to the warehouse for approval, like any stock request.
    sr = rm.post("/stock-requests", {"location_id": shop.id, "submit": True, "notes": "First order for a new dealer",
                                     "lines": [{"product_id": p.id, "quantity": 4}]}).json()
    assert sr["status"] == "SUBMITTED"
    told = world.db.execute(select(Notification.user_id).where(
        Notification.title == f"{sr['number']} is waiting for approval")).scalars().all()
    assert world.warehouse_op.id in told
    assert world.bal(shop, p).on_hand == 0          # nothing at the shop until it is approved and delivered


def test_an_existing_dealer_records_the_stock_they_already_hold(world):
    r = _create(world, True, "Henderson Tyres")
    assert r["joined_with_stock"] is True
    shop = _shop(world, r)
    world.api(world.manager).post(f"/resellers/{r['id']}/initial-stock", {
        "location_id": shop.id, "lines": [{"product_id": world.p1.id, "quantity": 3}]})
    assert world.bal(shop, world.p1).on_hand == 3
    h = world.api(world.manager).get(f"/resellers/{r['id']}/history-summary").json()
    assert h["dealer_type"] == "EXISTING"


def test_dealers_added_before_this_change_are_unaffected(world):
    # world.reseller_a was created without the choice (None): initial stock still works as before.
    world.api(world.manager).post(f"/resellers/{world.reseller_a.id}/initial-stock", {
        "location_id": world.loc_a.id, "lines": [{"product_id": world.p1.id, "quantity": 2}]})
    assert world.bal(world.loc_a, world.p1).on_hand == 2
