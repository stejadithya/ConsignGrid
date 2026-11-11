"""Release 1.11, finding 5 / D2: TyreGrow counts tyres and Xero holds prices. Sales of unpriced tyres succeed and
the product import works without price columns."""

import base64
import io
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import Workbook

from tests.factories import make_product, set_stock

pytestmark = pytest.mark.usefixtures("ledger_balanced")   # every test ends with the ledger reconciled


def _unpriced(world, sku):
    p = make_product(world.db, sku)
    p.list_price = None
    p.rrp = None
    world.db.flush()
    return p


def test_sale_of_an_unpriced_tyre_succeeds_at_zero(world):
    p = _unpriced(world, "NP-001")
    set_stock(world.db, world.loc_a, p, 3)
    world.db.commit()
    sale = world.api(world.user_a).post("/sales", {"location_id": world.loc_a.id, "sale_date": str(date.today()),
                                                  "lines": [{"product_id": p.id, "quantity": 1}]}, expected=201).json()
    line = sale["lines"][0]
    assert (Decimal(line["unit_price"]), line["price_source"]) == (Decimal("0.00"), "NOT_PRICED")
    assert world.bal(world.loc_a, p).on_hand == 2


def test_cash_sale_of_an_unpriced_tyre_succeeds_at_zero(world):
    p = _unpriced(world, "NP-002")
    set_stock(world.db, world.warehouse, p, 4)
    world.db.commit()
    sale = world.api(world.warehouse_op).post("/sales/cash", {"sale_date": str(date.today()),
                                                             "lines": [{"product_id": p.id, "quantity": 2}]},
                                              expected=201).json()
    assert {(ln["price_source"], Decimal(ln["unit_price"])) for ln in sale["lines"]} == {("NOT_PRICED", Decimal("0.00"))}
    assert world.bal(world.warehouse, p).on_hand == 2
    assert world.api(world.warehouse_op).get("/inventory/reconciliation").json()["balanced"] is True


def test_import_without_price_columns(world):
    wb = Workbook()
    wb.active.append(["SKU Code", "SKU Description"])
    wb.active.append(["NP-100", "205/55R16 ECODRIVE TL 91H CEAT"])
    buf = io.BytesIO()
    wb.save(buf)
    res = world.api(world.warehouse_op).post("/products/import", {
        "filename": "skus.xlsx", "content_base64": base64.b64encode(buf.getvalue()).decode(), "commit": True}).json()
    assert res["summary"]["create"] == 1 and res["summary"]["error"] == 0 and res["notes"] == []
    assert res["result"]["created"] == 1
    row = res["rows"][0]
    assert "dealer_price" not in row and "rrp" not in row
