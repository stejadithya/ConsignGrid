"""Release 1.11 — sale → invoice record → Xero (findings 24–26, D12): the Xero number is required to mark a record as
invoiced, and who sees invoice numbers and Xero numbers."""

from datetime import date

import pytest

from app.core.permissions import Role
from tests.factories import make_user, set_stock

pytestmark = pytest.mark.usefixtures("ledger_balanced")   # every test ends with the ledger reconciled

TODAY = date.today().isoformat()


def _sold(world, qty=3):
    set_stock(world.db, world.loc_a, world.p1, 10)
    world.db.commit()
    return world.api(world.user_a).post("/sales", {"location_id": world.loc_a.id, "sale_date": TODAY,
                                                    "lines": [{"product_id": world.p1.id, "quantity": qty}]},
                                        expected=201).json()


def _state(world, user, sale):
    return world.api(user).get(f"/sales/{sale['id']}").json()["lines"][0]


def test_marking_invoiced_needs_the_xero_number(world):
    sale = _sold(world)
    rm = world.api(world.manager)
    inv = rm.post("/invoices", {"reseller_id": world.reseller_a.id}, expected=201).json()
    rm.post(f"/invoices/{inv['id']}/issue", {}, expected=422)
    rm.post(f"/invoices/{inv['id']}/issue", {"xero_reference": ""}, expected=422)
    rm.post(f"/invoices/{inv['id']}/issue", {"xero_reference": "X" * 101}, expected=422)
    rm.post(f"/invoices/{inv['id']}/issue", {"xero_reference": "   "}, expected=422)
    out = rm.post(f"/invoices/{inv['id']}/issue", {"xero_reference": " INV-X-1001 "}).json()
    assert (out["status"], out["external_reference"], out["xero_reference"]) == ("ISSUED", "INV-X-1001", "INV-X-1001")
    assert out["xero_recorded_by"] == "Morgan Manager" and out["xero_recorded_at"]
    assert _state(world, world.manager, sale)["invoice_state"] == "INVOICED"
    rm.post(f"/invoices/{inv['id']}/issue", {"xero_reference": "INV-X-1002"}, expected=409)   # already invoiced
    # Corrected later, with the change recorded.
    fixed = rm.put(f"/invoices/{inv['id']}/external-reference", {"external_reference": "INV-X-1002"}).json()
    assert fixed["xero_reference"] == "INV-X-1002"
    audit = rm.get("/audit-events", params={"entity_type": "invoice", "entity_id": inv["id"]}).json()
    assert any("INV-X-1002 (was INV-X-1001)" in a["summary"] for a in audit)
    world.api(world.warehouse_op).put(f"/invoices/{inv['id']}/external-reference",
                                      {"external_reference": "NOPE"}, expected=403)


@pytest.mark.parametrize("role,number,xero", [
    ("rm", True, True), ("fm", True, True), ("admin", True, True),
    ("wm", False, False), ("rep", False, False), ("dealer", True, False),
])
def test_who_sees_invoice_and_xero_numbers(world, role, number, xero):
    sale = _sold(world)
    rm = world.api(world.manager)
    inv = rm.post("/invoices", {"reseller_id": world.reseller_a.id}).json()
    rm.post(f"/invoices/{inv['id']}/issue", {"xero_reference": "INV-X-1001"})
    users = {
        "rm": world.manager, "wm": world.warehouse_op, "rep": world.rep, "dealer": world.user_a,
        "fm": make_user(world.db, Role.FINANCE_MANAGER, "fm@example.com"),
        "admin": make_user(world.db, Role.ADMINISTRATOR, "root@example.com"),
    }
    world.db.commit()
    user = users[role]
    line = _state(world, user, sale)
    assert (line["invoice_state"], line["invoiced"]) == ("INVOICED", True)                # everyone sees the state
    assert line["invoice_number"] == (inv["number"] if number else None)
    assert line["xero_reference"] == ("INV-X-1001" if xero else None)
    assert "INV-X-1001" not in str(world.api(user).get("/sales").json()) or xero
    if role in ("wm", "rep"):
        world.api(user).get(f"/invoices/{inv['id']}", expected=403)                     # no invoice screens
    else:
        rec = world.api(user).get(f"/invoices/{inv['id']}").json()
        assert rec["external_reference"] == rec["xero_reference"] == ("INV-X-1001" if xero else None)
        assert (rec["xero_recorded_by"] is not None) == xero


def test_invoice_state_through_the_lifecycle(world):
    sale = _sold(world)
    rm = world.api(world.manager)
    for user in (world.warehouse_op, world.user_a, world.manager):
        assert _state(world, user, sale)["invoice_state"] == "NOT_INVOICED"
    inv = rm.post("/invoices", {"reseller_id": world.reseller_a.id}).json()
    line = _state(world, world.warehouse_op, sale)
    assert (line["invoice_state"], line["invoiced"], line["invoice_number"]) == ("INVOICE_DRAFTED", False, None)
    rm.post(f"/invoices/{inv['id']}/issue", {"xero_reference": "INV-X-7"})
    line = _state(world, world.manager, sale)
    assert (line["invoice_state"], line["invoiced"], line["xero_reference"]) == ("INVOICED", True, "INV-X-7")
    assert line["invoiced_at"]


def test_void_releases_the_lines(world):
    sale = _sold(world)
    rm = world.api(world.manager)
    inv = rm.post("/invoices", {"reseller_id": world.reseller_a.id}).json()
    rm.post(f"/invoices/{inv['id']}/issue", {"xero_reference": "INV-X-9"})
    rm.post(f"/invoices/{inv['id']}/void", {"reason": "Raised against the wrong dealer"})
    line = _state(world, world.manager, sale)
    assert (line["invoice_state"], line["invoice_number"], line["xero_reference"]) == ("NOT_INVOICED", None, None)
    again = rm.post("/invoices", {"reseller_id": world.reseller_a.id}, expected=201).json()
    assert again["number"] != inv["number"] and again["lines"][0]["sale_line_id"] == sale["lines"][0]["id"]
