"""Release 1.11 notifications that grab attention (finding 4): latest_id and after_id let the client spot new items."""

import pytest

from tests.factories import set_stock

pytestmark = pytest.mark.usefixtures("ledger_balanced")   # every test ends with the ledger reconciled


def _raise_request(world, qty=1):
    return world.api(world.user_a).post("/stock-requests", {
        "location_id": world.loc_a.id, "submit": True, "lines": [{"product_id": world.p1.id, "quantity": qty}]}).json()


def test_latest_id_and_after_id(world):
    set_stock(world.db, world.warehouse, world.p1, 5)
    world.db.commit()
    wm = world.api(world.warehouse_op)
    assert wm.get("/notifications/unread-count").json() == {"unread": 0, "latest_id": 0}
    first = _raise_request(world)
    c1 = wm.get("/notifications/unread-count").json()
    assert c1["unread"] == 1 and c1["latest_id"] > 0
    assert wm.get("/notifications", params={"after_id": c1["latest_id"]}).json() == []
    second = _raise_request(world)
    newer = wm.get("/notifications", params={"after_id": c1["latest_id"]}).json()
    assert [n["title"] for n in newer] == [f"{second['number']} is waiting for approval"]
    assert first["number"] != second["number"]
    c2 = wm.get("/notifications/unread-count").json()
    assert c2 == {"unread": 2, "latest_id": newer[0]["id"]}
    # Reading does not change latest_id; other users' notifications never leak in.
    wm.post("/notifications/read-all")
    assert wm.get("/notifications/unread-count").json() == {"unread": 0, "latest_id": newer[0]["id"]}
    assert world.api(world.user_b).get("/notifications", params={"after_id": 0}).json() == []
