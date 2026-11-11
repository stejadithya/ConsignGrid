"""Release 1.11 — report by dealer, by SKU (finding 31): the numbers match the ledger, and dealers see only their own."""

from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook

from tests.factories import set_stock, set_target

pytestmark = pytest.mark.usefixtures("ledger_balanced")   # every test ends with the ledger reconciled

TODAY = date.today().isoformat()


def _seed(world):
    """Alpha holds 10 of TYR-001 and sells 2 + 1; the first sale is invoiced in Xero. The replacements need 3 and the
    warehouse has 2: those are reserved and shipped, 1 is still waiting. Bravo holds 4 of TYR-002."""
    db = world.db
    set_stock(db, world.warehouse, world.p1, 2)
    set_stock(db, world.loc_a, world.p1, 10)
    set_stock(db, world.loc_b, world.p2, 4)
    set_target(db, world.loc_a, world.p1, 10)
    db.commit()
    dealer, rm, wm = world.api(world.user_a), world.api(world.manager), world.api(world.warehouse_op)
    first = dealer.post("/sales", {"location_id": world.loc_a.id, "sale_date": TODAY,
                                   "lines": [{"product_id": world.p1.id, "quantity": 2}]}, expected=201).json()
    dealer.post("/sales", {"location_id": world.loc_a.id, "sale_date": TODAY,
                           "lines": [{"product_id": world.p1.id, "quantity": 1}]}, expected=201)
    inv = rm.post("/invoices", {"reseller_id": world.reseller_a.id,
                                "sale_line_ids": [first["lines"][0]["id"]]}, expected=201).json()
    rm.post(f"/invoices/{inv['id']}/issue", {"xero_reference": "INV-X-1"})
    # Replacements: 3 required, the warehouse holds 2 → 2 reserved (auto-allocated) and shipped, 1 waiting.
    reqs = [r for r in wm.get("/replenishment/requests", params={"location_id": world.loc_a.id}).json()]
    allocated = [r for r in reqs if r["qty_allocated"]]
    for r in allocated:
        wm.post(f"/replenishment/requests/{r['id']}/ship", {"shipping_method": "COURIER", "carrier": "FastFreight"},
                expected=201)
    return reqs


def _row(report, dealer, sku):
    group = next(g for g in report["dealers"] if g["reseller_name"] == dealer)
    return group, next(r for r in group["rows"] if r["sku"] == sku)


def test_numbers_match_the_ledger(world):
    reqs = _seed(world)
    report = world.api(world.manager).get("/reports/dealer-sku").json()
    alpha, row = _row(report, "Alpha Tyres", "TYR-001")
    b = world.bal(world.loc_a, world.p1)
    assert (row["on_hand"], row["available"], row["held"]) == (b.on_hand, b.available, b.reserved + b.blocked) == (7, 7, 0)
    assert row["on_the_way"] == sum(r["qty_in_transit"] for r in world.api(world.manager).get(
        "/replenishment/requests", params={"location_id": world.loc_a.id}).json()) == 2
    assert row["waiting"] == 1 and sum(r["qty_required"] for r in reqs) == 3
    assert (row["sold"], row["invoiced"], row["not_invoiced"]) == (3, 2, 1)
    assert (row["shop"], row["city"], alpha["account_ref"]) == (world.loc_a.name, world.loc_a.city, "RA")
    assert alpha["totals"]["sold"] == 3 and alpha["totals"]["on_hand"] == 7
    _, bravo = _row(report, "Bravo Auto", "TYR-002")
    assert (bravo["on_hand"], bravo["sold"]) == (4, 0)
    assert report["totals"]["on_hand"] == 11
    assert "price" not in str(report).lower()
    # Outside the period nothing was sold.
    old = world.api(world.manager).get("/reports/dealer-sku", params={"date_from": "2020-01-01",
                                                                      "date_to": "2020-01-31"}).json()
    _, row = _row(old, "Alpha Tyres", "TYR-001")
    assert (row["sold"], row["on_hand"]) == (0, 7)


def test_dealers_see_only_their_own(world):
    _seed(world)
    mine = world.api(world.user_a).get("/reports/dealer-sku").json()
    assert [g["reseller_name"] for g in mine["dealers"]] == ["Alpha Tyres"]
    world.api(world.user_a).get("/reports/dealer-sku", params={"reseller_id": world.reseller_b.id}, expected=404)
    world.api(world.user_a).get("/reports/dealer-sku", params={"location_id": world.loc_b.id}, expected=404)
    assert [g["reseller_name"] for g in world.api(world.user_b).get("/reports/dealer-sku").json()["dealers"]] == ["Bravo Auto"]
    # Staff filter by dealer.
    only_b = world.api(world.warehouse_op).get("/reports/dealer-sku", params={"reseller_id": world.reseller_b.id}).json()
    assert [g["reseller_name"] for g in only_b["dealers"]] == ["Bravo Auto"]


def test_excel_download_has_the_same_numbers(world):
    _seed(world)
    res = world.api(world.manager).get("/reports/dealer-sku.xlsx")
    assert res.headers["content-type"].startswith("application/vnd.openxmlformats")
    ws = load_workbook(BytesIO(res.content)).active
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=4)]
    alpha = next(r for r in rows if r[0] == "Alpha Tyres" and r[4] == "TYR-001")
    assert alpha[6:] == [7, 7, 0, 2, 1, 3, 2, 1]
    assert any(r[0] == "Total Alpha Tyres" for r in rows) and rows[-1][0] == "Total, all dealers"
    mine = world.api(world.user_a).get("/reports/dealer-sku.xlsx")
    assert "Bravo" not in str([[c.value for c in r] for r in load_workbook(BytesIO(mine.content)).active.iter_rows()])
