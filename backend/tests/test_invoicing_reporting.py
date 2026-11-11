"""Phase 4: invoicing (traceability, duplicates, snapshots) and mandatory reports."""

import threading
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.core.db import session_factory
from app.core.errors import ConflictError
from app.modules.identity.models import User
from app.modules.invoicing import service as invoicing
from app.modules.invoicing.models import Invoice, InvoiceLine
from tests.factories import HANDOVER, set_stock, set_target

TODAY = date.today().isoformat()


def _sale(api, location, product, qty, **extra):
    return api.post("/sales", {"location_id": location.id, "sale_date": TODAY,
                               "lines": [{"product_id": product.id, "quantity": qty, **extra}]}).json()


def test_invoice_from_sale_with_snapshot_and_no_duplicates(world):
    db, rep, fin = world.db, world.api(world.rep), world.api(world.finance)
    set_stock(db, world.warehouse, world.p1, 50)
    set_stock(db, world.loc_a, world.p1, 20)
    set_target(db, world.loc_a, world.p1, 20)
    db.commit()
    fin.post(f"/resellers/{world.reseller_a.id}/prices",
             {"product_id": world.p1.id, "unit_price": "150.00", "valid_from": "2020-01-01"})
    sale = _sale(rep, world.loc_a, world.p1, 8)
    line = sale["lines"][0]
    assert line["unit_price"] == "150.00" and line["price_source"] == "CUSTOMER_PRICE"

    rep.post("/invoices", {"reseller_id": world.reseller_a.id}, expected=403)  # reps cannot invoice
    unin = fin.get("/invoices/uninvoiced", params={"reseller_id": world.reseller_a.id}).json()
    assert [(u["sale_number"], u["quantity"], u["line_net"]) for u in unin] == [(sale["number"], 8, "1200.00")]

    inv = fin.post("/invoices", {"reseller_id": world.reseller_a.id}, expected=201).json()
    assert inv["status"] == "DRAFT"
    assert (inv["subtotal"], inv["tax_total"], inv["total"]) == ("1200.00", "120.00", "1320.00")
    assert inv["lines"][0]["sale_number"] == sale["number"] and inv["lines"][0]["tax_code"] == "STD"
    assert inv["bill_to_account_ref"] == "RA"
    # A second invoice for the same sale is impossible.
    fin.post("/invoices", {"reseller_id": world.reseller_a.id}, expected=422)  # nothing left to invoice
    r = fin.post("/invoices", {"reseller_id": world.reseller_a.id, "sale_line_ids": [line["id"]]}, expected=409)
    assert "already" in r.json()["detail"]

    inv = fin.post(f"/invoices/{inv['id']}/issue", {"xero_reference": "INV-X-1"}).json()
    assert inv["status"] == "ISSUED"
    # D12: the rep sees that it is invoiced, not the number; the invoicing roles see the number.
    rep_line = rep.get(f"/sales/{sale['id']}").json()["lines"][0]
    assert (rep_line["invoice_state"], rep_line["invoiced"], rep_line["invoice_number"]) == ("INVOICED", True, None)
    assert fin.get(f"/sales/{sale['id']}").json()["lines"][0]["invoice_number"] == inv["number"]

    # Replenishment delivery happens after invoicing and creates no further invoice lines.
    rid = line["replenishment"][0]["id"]
    d = world.api(world.warehouse_op).post("/replenishment/deliveries", {
        "to_location_id": world.loc_a.id, "lines": [{"request_id": rid}]}).json()
    rep.post(f"/replenishment/deliveries/{d['id']}/receive", HANDOVER)
    assert world.bal(world.loc_a, world.p1).on_hand == 20
    assert db.execute(select(func.count()).select_from(InvoiceLine)).scalar_one() == 1
    assert db.execute(select(func.count()).select_from(Invoice)).scalar_one() == 1

    # Later price and tax changes do not alter the issued invoice.
    world.api(world.warehouse_op).patch(f"/products/{world.p1.id}", {"list_price": "999.00"})
    fin.put(f"/tax-rates/{world.tax.id}", {"code": "STD", "name": "Standard", "rate": "0.2000", "is_default": True})
    again = fin.get(f"/invoices/{inv['id']}").json()
    assert again["total"] == "1320.00" and again["lines"][0]["unit_price"] == "150.00"

    # Invoiced sales cannot be silently reversed.
    fin.post(f"/sales/lines/{line['id']}/reverse", {"quantity": 1, "reason": "Oops"}, expected=409)


def test_void_releases_sale_lines_for_reinvoicing(world):
    db, rep, fin = world.db, world.api(world.rep), world.api(world.finance)
    set_stock(db, world.loc_b, world.p2, 5)
    db.commit()
    sale = _sale(rep, world.loc_b, world.p2, 2)
    inv = fin.post("/invoices", {"reseller_id": world.reseller_b.id}).json()
    fin.post(f"/invoices/{inv['id']}/issue", {"xero_reference": "INV-X-1"})
    world.api(world.warehouse_op).post(f"/invoices/{inv['id']}/void", {"reason": "x"}, expected=403)
    voided = fin.post(f"/invoices/{inv['id']}/void", {"reason": "Wrong billing entity"}).json()
    assert voided["status"] == "VOID" and all(not ln["is_active"] for ln in voided["lines"])
    assert rep.get(f"/sales/{sale['id']}").json()["lines"][0]["invoice_status"] == "UNINVOICED"
    inv2 = fin.post("/invoices", {"reseller_id": world.reseller_b.id}).json()
    assert inv2["number"] != inv["number"] and inv2["total"] == inv["total"]


def test_tax_rate_is_configurable_per_reseller(world):
    db, rep, fin = world.db, world.api(world.rep), world.api(world.finance)
    exempt = fin.post("/tax-rates", {"code": "EXEMPT", "name": "Exempt", "rate": "0"}).json()
    world.api(world.manager).patch(f"/resellers/{world.reseller_c.id}", {"tax_rate_id": exempt["id"]})
    set_stock(db, world.loc_c, world.p1, 5)
    db.commit()
    _sale(rep, world.loc_c, world.p1, 1)
    inv = fin.post("/invoices", {"reseller_id": world.reseller_c.id}).json()
    assert (inv["tax_total"], inv["total"], inv["lines"][0]["tax_code"]) == ("0.00", "180.00", "EXEMPT")


def test_manual_price_requires_reason(world):
    db, rep = world.db, world.api(world.rep)
    set_stock(db, world.loc_a, world.p1, 5)
    db.commit()
    rep.post("/sales", {"location_id": world.loc_a.id, "sale_date": TODAY,
                        "lines": [{"product_id": world.p1.id, "quantity": 1, "unit_price": "99.00"}]}, expected=422)
    s = _sale(rep, world.loc_a, world.p1, 1, unit_price="99.00", price_override_reason="Warranty goodwill")
    assert s["lines"][0]["price_source"] == "MANUAL"


def test_concurrent_invoicing_of_same_sale_line(world, db):
    rep = world.api(world.rep)
    set_stock(db, world.loc_a, world.p1, 5)
    db.commit()
    line_id = _sale(rep, world.loc_a, world.p1, 2)["lines"][0]["id"]
    barrier = threading.Barrier(2)
    outcomes = []

    def attempt():
        s = session_factory()()
        try:
            actor = s.get(User, world.finance.id)
            barrier.wait()
            invoicing.create_invoice(s, actor, reseller_id=world.reseller_a.id, sale_line_ids=[line_id])
            s.commit()
            outcomes.append("ok")
        except ConflictError:
            s.rollback()
            outcomes.append("conflict")
        finally:
            s.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(outcomes) == ["conflict", "ok"]
    assert db.execute(select(func.count()).select_from(InvoiceLine).where(InvoiceLine.is_active)).scalar_one() == 1


def test_accounting_export_boundary(world):
    db, rep, fin = world.db, world.api(world.rep), world.api(world.finance)
    set_stock(db, world.loc_a, world.p1, 5)
    db.commit()
    _sale(rep, world.loc_a, world.p1, 1)
    inv = fin.post("/invoices", {"reseller_id": world.reseller_a.id}).json()
    fin.post(f"/invoices/{inv['id']}/export", expected=409)  # drafts are not exported
    fin.post(f"/invoices/{inv['id']}/issue", {"xero_reference": "INV-X-1"})
    payload = fin.post(f"/invoices/{inv['id']}/export").json()
    assert payload["schema"] == "invoice.v1" and payload["customer"]["account_ref"] == "RA"
    assert payload["lines"][0]["source"]["sale_number"].startswith("SAL-")
    out = fin.put(f"/invoices/{inv['id']}/external-reference", {"external_reference": "ACC-12345"}).json()
    assert out["external_reference"] == "ACC-12345" and out["exported_at"]


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def _build_activity(world):
    db, rep, mgr = world.db, world.api(world.rep), world.api(world.manager)
    set_stock(db, world.warehouse, world.p1, 3)
    set_stock(db, world.loc_a, world.p1, 10)
    set_stock(db, world.loc_a, world.p3, 6)
    set_stock(db, world.loc_b, world.p1, 4)
    set_target(db, world.loc_a, world.p1, 10)
    db.commit()
    sale = _sale(rep, world.loc_a, world.p1, 5)            # 3 allocated from warehouse, 2 awaiting supply
    t = rep.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p3.id,
                                "quantity": 2, "reason": "Urgent pair"}).json()
    mgr.post(f"/transfers/{t['id']}/approve", {"source_location_id": world.loc_a.id, "approval_notes": "OK"})
    rep.post(f"/transfers/{t['id']}/collect", {})
    return sale, t


def test_report_total_consignment_stock(world):
    sale, t = _build_activity(world)   # transfer still in transit
    mgr = world.api(world.manager)
    rpt = mgr.get("/reports/consignment-stock").json()
    by = {(r["location_code"], r["sku"]): r for r in rpt["rows"]}
    assert by[("RA-MAIN", "TYR-001")]["on_hand"] == 5    # sold stock excluded
    assert by[("RA-MAIN", "TYR-003")]["on_hand"] == 4    # collected stock left the source
    assert ("RB-MAIN", "TYR-003") not in by               # not yet received: not double counted
    assert rpt["in_transit_total"] == 2
    assert rpt["totals"]["on_hand"] == 5 + 4 + 4
    assert rpt["totals"]["value"] == "1600.00"  # cost value: 5×120 + 4×130 + 4×120
    # Rep has no cost permission → no value.
    assert world.api(world.rep).get("/reports/consignment-stock").json()["totals"]["value"] is None
    # Filters.
    only_a = mgr.get("/reports/consignment-stock", params={"reseller_id": world.reseller_a.id}).json()
    assert {r["location_code"] for r in only_a["rows"]} == {"RA-MAIN"}
    by_brand = mgr.get("/reports/consignment-stock", params={"brand": "continental"}).json()
    assert {r["sku"] for r in by_brand["rows"]} == {"TYR-003"}


def test_report_backorders_distinguishes_allocated_from_awaiting(world):
    sale, t = _build_activity(world)
    rpt = world.api(world.manager).get("/reports/backorders").json()
    by_reason = {r["reason"]: r for r in rpt["rows"]}
    assert (by_reason["SALE"]["qty_allocated"], by_reason["SALE"]["qty_awaiting_supply"]) == (3, 2)
    assert (by_reason["TRANSFER"]["qty_awaiting_supply"], by_reason["TRANSFER"]["reseller_id"]) == \
        (2, world.reseller_a.id)
    assert rpt["totals"] == {"requests": 2, "qty_outstanding": 7, "qty_allocated": 3, "qty_in_transit": 0,
                             "qty_transfer_covered": 0, "qty_awaiting_supply": 4}
    assert rpt["by_reason"] == {"SALE": 5, "TRANSFER": 2}
    # Reseller B sees none of A's backorders.
    assert world.api(world.user_b).get("/reports/backorders").json()["rows"] == []


def test_report_reseller_transaction_history(world):
    sale, t = _build_activity(world)
    rep = world.api(world.rep)
    rep.post(f"/transfers/{t['id']}/receive", HANDOVER)
    fin = world.api(world.finance)
    inv = fin.post("/invoices", {"reseller_id": world.reseller_a.id}).json()
    fin.post(f"/invoices/{inv['id']}/issue", {"xero_reference": "INV-X-1"})

    h = rep.get(f"/reports/resellers/{world.reseller_a.id}/transactions").json()
    cats = [(r["category"], r["sku"], r["qty_in"], r["qty_out"], r["running_balance"]) for r in h["rows"]]
    assert cats == [
        ("OPENING_BALANCE", "TYR-001", 10, 0, 10),
        ("OPENING_BALANCE", "TYR-003", 6, 0, 6),
        ("SALE", "TYR-001", 0, 5, 5),
        ("TRANSFER_OUT", "TYR-003", 0, 2, 4),
    ]
    sale_row = h["rows"][2]
    assert sale_row["reference_number"] == sale["number"] and sale_row["invoice_numbers"] == [inv["number"]]
    tr = h["rows"][3]["transfer"]
    assert tr["number"] == t["number"] and "Bravo Auto" in tr["destination"] and tr["approved_by"] == "Morgan Manager"
    assert tr["linked_backorder"] and tr["linked_backorder"].startswith("REP-")
    assert h["outstanding_by_reason"] == {"SALE": 5, "TRANSFER": 2}

    hb = rep.get(f"/reports/resellers/{world.reseller_b.id}/transactions").json()
    assert [r["category"] for r in hb["rows"]] == ["OPENING_BALANCE", "TRANSFER_IN"]
    # Reseller isolation on history.
    world.api(world.user_b).get(f"/reports/resellers/{world.reseller_a.id}/transactions", expected=404)
    assert world.api(world.user_a).get(f"/reports/resellers/{world.reseller_a.id}/transactions").json()["rows"]


def test_report_history_opening_balance_for_period(world):
    _build_activity(world)
    tomorrow = date.fromordinal(date.today().toordinal() + 1).isoformat()
    h = world.api(world.rep).get(f"/reports/resellers/{world.reseller_a.id}/transactions",
                                 params={"date_from": tomorrow}).json()
    assert h["rows"] == []
    assert {(o["sku"], o["quantity"]) for o in h["opening_balances"]} == {("TYR-001", 5), ("TYR-003", 4)}


def test_dashboard_and_additional_reports(world):
    _build_activity(world)
    mgr = world.api(world.manager)
    d = mgr.get("/reports/dashboard").json()
    assert d["warehouse"] == {"on_hand": 3, "reserved": 3, "blocked": 0, "available": 0}
    assert d["consignment"]["on_hand"] == 13 and d["in_transit"] == 2
    assert d["backorders"]["qty_awaiting_supply"] == 4
    assert d["awaiting_dispatch_qty"] == 3
    assert d["transfers_in_progress"]["in_transit"] == 1
    assert d["sales_awaiting_invoicing"] == {"qty": 5, "value": "900.00"}
    demand = {r["sku"]: r for r in mgr.get("/reports/demand-by-sku").json()}
    assert demand["TYR-001"]["awaiting_supply"] == 2 and demand["TYR-003"]["transfer"] == 2
    wh = {r["sku"]: r for r in mgr.get("/reports/warehouse-availability").json()}
    assert wh["TYR-001"]["reserved"] == 3 and wh["TYR-003"]["awaiting_supply_demand"] == 2
    un = mgr.get("/reports/uninvoiced-sales").json()
    assert un[0]["reseller_name"] == "Alpha Tyres" and un[0]["uninvoiced_qty"] == 5
    assert mgr.get("/reports/consignment-ageing").json()
    # Reseller dashboard is scoped and hides dealership-wide warehouse figures.
    da = world.api(world.user_a).get("/reports/dashboard").json()
    assert da["warehouse"] is None and da["consignment"]["on_hand"] == 9
    world.api(world.user_a).get("/reports/warehouse-availability", expected=403)
    assert Decimal(d["sales_awaiting_invoicing"]["value"]) == Decimal("900.00")
