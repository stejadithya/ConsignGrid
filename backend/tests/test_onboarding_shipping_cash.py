"""Initial stock for existing resellers, "Latest stock", shipping with a sales rep, delivery notes, cash sales."""

from datetime import date

import pytest

from app.core.config import get_settings
from app.core.permissions import Role
from tests.factories import HANDOVER, make_user, set_stock

TODAY = str(date.today())


def test_initial_stock_for_existing_reseller(world):
    rm, sr = world.api(world.manager), world.api(world.rep)
    body = {"location_id": world.loc_a.id, "lines": [{"product_id": world.p1.id, "quantity": 6},
                                                     {"product_id": world.p2.id, "quantity": 2}]}
    res = rm.post(f"/resellers/{world.reseller_a.id}/initial-stock", body, expected=201).json()
    assert res["units"] == 8
    assert world.bal(world.loc_a, world.p1).on_hand == 6
    world.api(world.warehouse_op).post(f"/resellers/{world.reseller_a.id}/initial-stock",
                                       {**body, "lines": [{"product_id": world.p3.id, "quantity": 1}]}, expected=201)
    sr.post(f"/resellers/{world.reseller_a.id}/initial-stock", body, expected=403)
    world.api(world.user_a).post(f"/resellers/{world.reseller_a.id}/initial-stock", body, expected=403)
    # Only this reseller's consignment locations.
    rm.post(f"/resellers/{world.reseller_a.id}/initial-stock", {**body, "location_id": world.loc_b.id}, expected=422)
    rm.post(f"/resellers/{world.reseller_a.id}/initial-stock", {**body, "location_id": world.warehouse.id}, expected=422)
    hist = rm.get(f"/reports/resellers/{world.reseller_a.id}/transactions").json()
    assert {r["category"] for r in hist["rows"]} == {"OPENING_BALANCE"}   # shown as "Initial stock (backorder)"


def test_latest_stock_flag_only_for_tyres_never_held(world):
    db = world.db
    set_stock(db, world.loc_a, world.p1, 5)   # already holds p1
    db.commit()
    sr = world.api(world.rep)
    held = sr.post("/replenishment/requests", {"location_id": world.loc_a.id, "product_id": world.p1.id,
                                               "quantity": 1, "reason": "More"}, expected=(201, 422))
    rm = world.api(world.manager)
    new = rm.post("/replenishment/requests", {"location_id": world.loc_a.id, "product_id": world.p2.id, "quantity": 2,
                                              "reason": "New line"}, expected=201).json()
    assert new["first_supply"] is True
    again = rm.post("/replenishment/requests", {"location_id": world.loc_a.id, "product_id": world.p1.id, "quantity": 1,
                                                "reason": "Top up"}, expected=201).json()
    assert again["first_supply"] is False
    assert held.status_code in (201, 422)


def _allocated_request(world, qty=2):
    db = world.db
    set_stock(db, world.warehouse, world.p1, 10)
    db.commit()
    req = world.api(world.manager).post("/replenishment/requests", {
        "location_id": world.loc_a.id, "product_id": world.p1.id, "quantity": qty, "reason": "Stock"}).json()
    assert req["qty_allocated"] == qty
    return req


def test_ship_with_sales_rep_and_download_delivery_note(world):
    world.reseller_a.email = "owner@alpha.example.com"
    req = _allocated_request(world)
    wm = world.api(world.warehouse_op)
    body = {"to_location_id": world.loc_a.id, "lines": [{"request_id": req["id"], "quantity": 2}],
            "shipping_method": "SALES_REP"}
    wm.post("/replenishment/deliveries", body, expected=422)   # which rep?
    wm.post("/replenishment/deliveries", {**body, "carried_by_user_id": world.manager.id}, expected=422)  # not a rep
    d = wm.post("/replenishment/deliveries", {**body, "carried_by_user_id": world.rep.id}, expected=201).json()
    assert d["shipping_method"] == "SALES_REP" and d["carried_by"] == world.rep.full_name
    assert d["carrier_reference"] == f"Sales representative: {world.rep.full_name}"
    assert any(n["title"] == f"Please deliver {d['number']}" for n in world.api(world.rep).get("/notifications").json())
    # The rep confirms the handover; without SMTP the email is recorded as not set up and nothing is sent.
    d = world.api(world.rep).post(f"/replenishment/deliveries/{d['id']}/receive", {**HANDOVER, "lines": []}).json()
    assert d["status"] == "RECEIVED" and d["note_emailed_at"] is None and "not set up" in d["note_email_error"]
    pdf = world.api(world.user_a).get(f"/replenishment/deliveries/{d['id']}/delivery-note.pdf")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content[:5] == b"%PDF-"
    world.api(world.user_b).get(f"/replenishment/deliveries/{d['id']}/delivery-note.pdf", expected=404)


class _FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        _FakeSMTP.sent.append(msg)


@pytest.fixture
def smtp(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(s, "smtp_from", "Acme Tyres <deliveries@example.com>")
    _FakeSMTP.sent = []
    monkeypatch.setattr("app.modules.delivery_notes.service.smtplib.SMTP", _FakeSMTP)
    return _FakeSMTP


def test_delivery_note_emailed_automatically_with_pdf(world, smtp):
    world.reseller_a.email = "owner@alpha.example.com"
    world.db.commit()
    req = _allocated_request(world, qty=3)
    wm = world.api(world.warehouse_op)
    d = wm.post("/replenishment/deliveries", {"to_location_id": world.loc_a.id, "carrier_reference": "StarTrack",
                                              "lines": [{"request_id": req["id"], "quantity": 3}]}).json()
    d = world.api(world.user_a).post(f"/replenishment/deliveries/{d['id']}/receive", {"lines": []}).json()
    assert d["note_email_to"] == "owner@alpha.example.com" and d["note_emailed_at"]
    [msg] = smtp.sent
    assert msg["To"] == "owner@alpha.example.com" and "3 tyre(s) delivered" in msg["Subject"]
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "within 14 days" in body and "Primacy 4" in body
    [att] = list(msg.iter_attachments())
    assert att.get_filename() == f"Delivery-note-{d['number']}.pdf"
    # Resend on request (staff only).
    res = world.api(world.manager).post(f"/replenishment/deliveries/{d['id']}/email-delivery-note").json()
    assert res["status"] == "sent" and len(smtp.sent) == 2
    world.api(world.user_a).post(f"/replenishment/deliveries/{d['id']}/email-delivery-note", expected=403)


def test_cash_sale_from_warehouse(world):
    db = world.db
    set_stock(db, world.warehouse, world.p1, 5)
    db.commit()
    wm = world.api(world.warehouse_op)
    body = {"sale_date": TODAY, "customer_name": "Corner Garage", "customer_phone": "021 555 123",
            "lines": [{"product_id": world.p1.id, "quantity": 2}]}
    sale = wm.post("/sales/cash", body, expected=201).json()
    assert sale["source"] == "CASH_SALE" and sale["customer_name"] == "Corner Garage"
    assert sale["reseller_name"] == "Cash sales (walk-in)" and sale["location_code"] == "WH-MAIN"
    line = sale["lines"][0]
    assert line["unit_price"] == "180.00" and line["replenishment"] == [] and line["invoice_status"] == "DRAFTED"
    assert world.bal(world.warehouse, world.p1).on_hand == 3
    # D12: the warehouse sees only the invoice state; the Relationship Manager sees the record's number.
    assert (line["invoice_state"], line["invoice_number"]) == ("INVOICE_DRAFTED", None)
    rm_line = world.api(world.manager).get(f"/sales/{sale['id']}").json()["lines"][0]
    invoices = world.api(world.manager).get("/invoices").json()
    inv = next(i for i in invoices if i["number"] == rm_line["invoice_number"])
    assert inv["status"] == "DRAFT" and inv["bill_to_name"] == "Corner Garage"
    # Price override needs a reason; reserved / missing stock cannot be sold; reps and resellers cannot sell for cash.
    wm.post("/sales/cash", {**body, "lines": [{"product_id": world.p1.id, "quantity": 1, "unit_price": "150"}]}, expected=422)
    wm.post("/sales/cash", {**body, "lines": [{"product_id": world.p1.id, "quantity": 9}]}, expected=409)
    world.api(world.rep).post("/sales/cash", body, expected=403)
    world.api(world.user_a).post("/sales/cash", body, expected=403)
    world.api(world.manager).post("/sales/cash", {**body, "lines": [
        {"product_id": world.p1.id, "quantity": 1, "unit_price": "150", "price_override_reason": "Loyal customer"}]})
    # The cash account is never listed as a reseller.
    assert all(r["account_ref"] != "CASH" for r in world.api(world.manager).get("/resellers").json())
    # A consignment sale can never be recorded as a cash sale.
    world.api(world.rep).post("/sales", {"location_id": world.loc_a.id, "sale_date": TODAY, "source": "CASH_SALE",
                                         "lines": [{"product_id": world.p1.id, "quantity": 1}]}, expected=(400, 422))


def test_sales_list_period_and_limit(world):
    db = world.db
    set_stock(db, world.loc_a, world.p1, 10)
    db.commit()
    alpha = world.api(world.user_a)
    for _ in range(3):
        alpha.post("/sales", {"location_id": world.loc_a.id, "sale_date": TODAY, "source": "RESELLER_REPORT",
                              "lines": [{"product_id": world.p1.id, "quantity": 1}]})
    rows = alpha.get("/sales", params={"date_from": TODAY, "date_to": TODAY, "limit": 5000}).json()
    assert len(rows) == 3
    assert alpha.get("/sales", params={"date_from": "2000-01-01", "date_to": "2000-01-31"}).json() == []


def test_administrator_can_add_initial_stock_and_cash_sale(world):
    db = world.db
    admin = make_user(db, Role.ADMINISTRATOR, "root2@example.com")
    set_stock(db, world.warehouse, world.p2, 2)
    db.commit()
    api = world.api(admin)
    api.post(f"/resellers/{world.reseller_b.id}/initial-stock",
             {"location_id": world.loc_b.id, "lines": [{"product_id": world.p2.id, "quantity": 1}]}, expected=201)
    api.post("/sales/cash", {"sale_date": TODAY, "lines": [{"product_id": world.p2.id, "quantity": 1}]}, expected=201)
