"""Dealer history summary (staff): joined when and with what stock, new or existing, first consignment, sales so far."""

from datetime import date, timedelta

import pytest

from app.core.permissions import Role
from tests.factories import HANDOVER, make_user, set_stock

pytestmark = pytest.mark.usefixtures("ledger_balanced")


def _sale(world, location, product, qty, when=None):
    return world.api(world.rep).post("/sales", {
        "location_id": location.id, "sale_date": (when or date.today()).isoformat(), "source": "RESELLER_REPORT",
        "source_reference": "Phone call", "lines": [{"product_id": product.id, "quantity": qty}]}).json()


def history(world, reseller, user=None, expected=200):
    return world.api(user or world.manager).get(f"/resellers/{reseller.id}/history-summary", expected=expected).json()


def test_existing_dealer_joined_with_stock_and_sales_so_far(world):
    db = world.db
    set_stock(db, world.loc_a, world.p1, 6)
    set_stock(db, world.loc_a, world.p2, 4)
    db.commit()
    _sale(world, world.loc_a, world.p1, 2, date.today() - timedelta(days=3))
    last = _sale(world, world.loc_a, world.p2, 3)
    world.api(world.finance).post(f"/sales/lines/{last['lines'][0]['id']}/reverse", {"quantity": 1, "reason": "Keyed wrong"})

    h = history(world, world.reseller_a)
    assert h["dealer_type"] == "EXISTING"
    assert h["onboarding_stock_kind"] == "INITIAL_STOCK"
    assert [(ln["sku"], ln["quantity"]) for ln in h["onboarding_stock"]] == [("TYR-001", 6), ("TYR-002", 4)]
    assert h["first_stock"]["txn_type"] == "OPENING_BALANCE"
    assert (h["units_sold"], h["sales_count"]) == (4, 2)                     # 2 + (3 − 1 reversed)
    assert (h["last_sale"]["number"], h["last_sale"]["units"], h["last_sale"]["sale_date"]) == \
        (last["number"], 2, date.today().isoformat())


def test_new_dealer_first_consignment_is_the_first_delivery(world):
    db, rep, mgr = world.db, world.api(world.rep), world.api(world.manager)
    set_stock(db, world.loc_a, world.p3, 5)
    db.commit()
    t = rep.post("/transfers", {"destination_location_id": world.loc_c.id, "product_id": world.p3.id, "quantity": 2,
                                "reason": "First stock"}).json()
    mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_a.id})
    rep.post(f"/transfers/{t['id']}/collect", {})
    rep.post(f"/transfers/{t['id']}/receive", HANDOVER)

    h = history(world, world.reseller_c)
    assert h["dealer_type"] == "NEW"
    assert h["onboarding_stock_kind"] == "FIRST_DELIVERY"
    assert [(ln["sku"], ln["quantity"]) for ln in h["onboarding_stock"]] == [("TYR-003", 2)]
    assert h["first_stock"]["txn_type"] == "TRANSFER_RECEIPT" and h["first_stock"]["reference_number"] == t["number"]
    assert (h["units_sold"], h["sales_count"], h["last_sale"]) == (0, 0, None)


def test_dealer_with_no_activity_and_who_added_them(world):
    created = world.api(world.manager).post("/resellers", {
        "business_name": "Delta Tyres", "contact_name": "Dee", "email": "dee@example.com", "phone": "09 555 0199",
        "billing_address": "4 Test Street", "sales_rep_user_id": world.rep.id,
        "locations": [{"name": "Main shop", "address_line1": "4 Test Street", "city": "Napier"}]}).json()
    h = world.api(world.manager).get(f"/resellers/{created['id']}/history-summary").json()
    assert h["onboarded_by"] == "Morgan Manager" and h["onboarded_at"]
    assert (h["dealer_type"], h["first_stock"], h["onboarding_stock_kind"], h["onboarding_stock"]) == ("NEW", None, None, [])
    assert (h["units_sold"], h["last_sale"]) == (0, None)


def test_only_warehouse_and_relationship_managers_and_administrators(world):
    admin = make_user(world.db, Role.ADMINISTRATOR, "root@example.com")
    fm = make_user(world.db, Role.FINANCE_MANAGER, "fm@example.com")
    world.db.commit()
    for user in (world.manager, world.warehouse_op, admin):
        history(world, world.reseller_a, user)
    for user in (world.rep, fm, world.user_a):
        history(world, world.reseller_a, user, expected=403)
    history(world, world.reseller_a.__class__(id=999999), expected=404)
