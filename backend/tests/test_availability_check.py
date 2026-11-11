"""Release 1.11, finding 7: journey-specific stock check for the tyres on a request."""

import pytest

from app.modules.customers.models import Location, LocationType
from tests.factories import set_stock

pytestmark = pytest.mark.usefixtures("ledger_balanced")   # every test ends with the ledger reconciled


def test_availability_check_figures(world):
    db = world.db
    second_shop = Location(code="RA-2", name="Alpha Second", type=LocationType.CONSIGNMENT, reseller_id=world.loc_a.reseller_id)
    db.add(second_shop)
    db.flush()
    set_stock(db, world.warehouse, world.p1, 12)
    set_stock(db, world.loc_a, world.p1, 7)
    set_stock(db, second_shop, world.p1, 2)
    set_stock(db, world.loc_b, world.p1, 4)
    db.commit()
    rows = world.api(world.warehouse_op).post("/inventory/availability-check", {
        "product_ids": [world.p1.id, world.p2.id], "dealer_location_id": world.loc_a.id}).json()
    p1, p2 = rows
    assert p1 == {"product_id": world.p1.id, "warehouse_available": 12, "warehouse_on_hand": 12,
                  "at_this_location": {"on_hand": 7, "available": 7}, "dealer_total_on_hand": 9,
                  "other_dealers": {"available": 4, "locations": 1}}
    assert p2["warehouse_available"] == 0 and p2["at_this_location"] == {"on_hand": 0, "available": 0}
    # Without a dealer location: warehouse and every dealer.
    plain = world.api(world.rep).post("/inventory/availability-check", {"product_ids": [world.p1.id]}).json()[0]
    assert plain["at_this_location"] is None and plain["dealer_total_on_hand"] is None
    assert plain["other_dealers"] == {"available": 13, "locations": 3}


def test_availability_check_is_staff_only(world):
    world.api(world.user_a).post("/inventory/availability-check", {"product_ids": [world.p1.id]}, expected=403)
    world.api(world.warehouse_op).post("/inventory/availability-check",
                                       {"product_ids": [world.p1.id], "dealer_location_id": world.warehouse.id},
                                       expected=404)
