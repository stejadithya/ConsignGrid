"""One search box across the app (global search, option B): documents by number, dealers, tyres and people.

Everyone only finds what they could already open; dealer users find only their own documents.
"""

from datetime import date

import pytest

from app.core.permissions import Role
from tests.factories import APPROVAL, make_user, set_stock

pytestmark = pytest.mark.usefixtures("ledger_balanced")


def find(world, user, q):
    return world.api(user).get("/search", params={"q": q}).json()


def _request(world, user, loc, qty=2):
    return world.api(user).post("/stock-requests", {"location_id": loc.id, "submit": True,
                                                    "lines": [{"product_id": world.p1.id, "quantity": qty}]}).json()


def test_a_document_is_found_by_its_number_however_it_is_typed(world):
    sr = _request(world, world.user_a, world.loc_a)
    n = sr["number"]                                    # e.g. SRQ-000001
    digits = n.split("-")[1].lstrip("0")
    for typed in (n, n.lower(), n.replace("-", " "), f"srq{digits}", f"SRQ-{digits}", n.split("-")[1]):
        docs = find(world, world.manager, typed)["documents"]
        top = docs[0]
        assert (top["type"], top["title"], top["href"]) == ("STOCK_REQUEST", n, f"/stock-requests/{sr['id']}"), typed
        assert top["subtitle"] == "Alpha Tyres"
    assert find(world, world.manager, n)["documents"][0]["exact"] is True
    assert find(world, world.manager, "sr")["documents"] == []     # under 3 characters: nothing


def test_dealers_only_find_their_own_documents_and_never_other_dealers(world):
    mine = _request(world, world.user_a, world.loc_a)
    theirs = _request(world, world.user_b, world.loc_b)
    assert [d["title"] for d in find(world, world.user_a, mine["number"])["documents"]] == [mine["number"]]
    assert find(world, world.user_a, theirs["number"])["documents"] == []
    res = find(world, world.user_a, "Bravo")
    assert res["dealers"] == [] and res["people"] == []
    assert "Bravo" not in str(find(world, world.user_a, "SRQ"))
    # A transfer to them never names the other dealer.
    set_stock(world.db, world.loc_b, world.p2, 3)
    world.db.commit()
    mgr = world.api(world.manager)
    t = mgr.post("/transfers", {"destination_location_id": world.loc_a.id, "product_id": world.p2.id, "quantity": 1,
                                "reason": "Customer waiting"}, expected=201).json()
    mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_b.id, "source_consent_reference": "ok"})
    [hit] = find(world, world.user_a, t["number"])["documents"]
    assert hit["subtitle"] == "Coming to you" and "Bravo" not in str(hit)
    assert find(world, world.manager, t["number"])["documents"][0]["subtitle"] == "Bravo Auto → Alpha Tyres"


def test_the_xero_number_is_found_only_by_those_allowed_to_see_it(world):
    set_stock(world.db, world.loc_a, world.p1, 3)
    world.db.commit()
    rep = world.api(world.rep)
    rep.post("/sales", {"location_id": world.loc_a.id, "sale_date": date.today().isoformat(), "source": "RESELLER_REPORT",
                        "source_reference": "Phone call", "lines": [{"product_id": world.p1.id, "quantity": 1}]})
    rm = world.api(world.manager)
    inv = rm.post("/invoices", {"reseller_id": world.reseller_a.id}, expected=201).json()
    rm.post(f"/invoices/{inv['id']}/issue", {"xero_reference": "XERO-7781"})
    fm = make_user(world.db, Role.FINANCE_MANAGER, "fm@example.com")
    world.db.commit()
    for user in (world.manager, fm):
        [hit] = find(world, user, "xero 7781")["documents"]
        assert (hit["type"], hit["title"], hit["exact"]) == ("INVOICE", inv["number"], True)
        assert "Xero XERO-7781" in hit["subtitle"]
    # The dealer finds their invoice record by its number, but not by (and never sees) the Xero number.
    assert find(world, world.user_a, "xero 7781")["documents"] == []
    [own] = find(world, world.user_a, inv["number"])["documents"]
    assert "XERO" not in str(own)
    # Staff without invoices (the Warehouse Manager) don't find invoice records at all.
    assert all(d["type"] != "INVOICE" for d in find(world, world.warehouse_op, inv["number"])["documents"])


def test_dealers_tyres_and_people(world):
    rm = world.api(world.manager)
    res = find(world, world.manager, "alpha")
    assert [d["title"] for d in res["dealers"]] == ["Alpha Tyres"] and res["dealers"][0]["href"].startswith("/resellers/")
    assert [d["title"] for d in find(world, world.manager, "RB-MAIN")["dealers"]] == ["Bravo Auto"]   # a shop code
    assert find(world, world.manager, "springfield")["dealers"]                               # a shop's city
    tyres = find(world, world.manager, "225 45")["tyres"]
    assert [t["subtitle"] for t in tyres] == ["TYR-002"]                                       # 225/45R17
    assert find(world, world.user_a, "225 45")["tyres"][0]["href"] == "/consignment?sku=TYR-002"
    people = find(world, world.manager, "riley")["people"]
    assert [p["title"] for p in people] == ["Riley Rep"] and people[0]["status"] == "ACTIVE"
    assert find(world, world.warehouse_op, "riley")["people"] == []                           # only user managers
    assert rm.get("/search").json()["documents"] == []


def test_each_group_needs_the_permission_its_screen_needs(world):
    sr = _request(world, world.user_a, world.loc_a, qty=1)
    set_stock(world.db, world.warehouse, world.p1, 5)
    world.db.commit()
    world.api(world.warehouse_op).post(f"/stock-requests/{sr['id']}/decision", {
        "lines": [{"line_id": sr["lines"][0]["id"], "approve_qty": 1}], "approval": APPROVAL})
    number = world.api(world.warehouse_op).post("/purchasing/purchase-orders", {
        "supplier_name": "CEAT NZ", "warehouse_location_id": world.warehouse.id,
        "lines": [{"product_id": world.p1.id, "qty_ordered": 4}]}).json()["number"]
    assert find(world, world.warehouse_op, number)["documents"][0]["type"] == "PURCHASE_ORDER"
    assert find(world, world.rep, number)["documents"] == []          # reps don't do purchasing
    assert find(world, world.user_a, number)["documents"] == []
    # Stock movements are for staff only.
    txn = find(world, world.warehouse_op, "TXN")["documents"]
    assert txn and all(d["type"] == "MOVEMENT" for d in txn)
    assert find(world, world.user_a, "TXN")["documents"] == []
