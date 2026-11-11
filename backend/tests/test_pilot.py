"""Pilot readiness: the four roles, backend-enforced access, reseller isolation, password change, feedback,
reference documents and the controlled clean-pilot reset."""

import argparse
import json
from datetime import date

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.permissions import ROLE_PERMISSIONS, P, Role
from app.modules.catalogue.models import Product, TaxRate
from app.modules.customers.models import Location, LocationType, Reseller
from app.modules.identity.models import User
from tests.factories import set_stock, set_target

TODAY = date.today().isoformat()

# ---------------------------------------------------------------------------
# Roles and the permission matrix
# ---------------------------------------------------------------------------


def test_only_four_business_roles_exist():
    assert {r.value for r in Role} == {"ADMINISTRATOR", "RELATIONSHIP_MANAGER", "WAREHOUSE_MANAGER", "SALES_REP",
                                       "RESELLER", "FINANCE_MANAGER"}
    assert set(ROLE_PERMISSIONS) == set(Role)


def test_permission_matrix_highlights():
    rm, wm, sr, rs = (ROLE_PERMISSIONS[r] for r in (Role.RELATIONSHIP_MANAGER, Role.WAREHOUSE_MANAGER,
                                                    Role.SALES_REP, Role.RESELLER))
    # Product master and warehouse stock: the Warehouse Manager, and the Relationship Manager above them (P-028).
    assert P.CATALOGUE_WRITE in wm and P.CATALOGUE_WRITE in rm and P.CATALOGUE_WRITE not in sr | rs
    assert P.CATALOGUE_CREATE in wm and P.CATALOGUE_CREATE in rm and P.CATALOGUE_CREATE not in sr | rs
    assert {P.INVENTORY_RECEIVE, P.INVENTORY_ADJUST, P.PURCHASING_MANAGE, P.DISPATCH} <= wm & rm
    assert not ({P.INVENTORY_RECEIVE, P.INVENTORY_ADJUST, P.PURCHASING_MANAGE, P.DISPATCH} & (sr | rs))
    # Invoicing belongs to the Relationship Manager.
    assert {P.INVOICE_CREATE, P.INVOICE_VOID} <= rm and not ({P.INVOICE_CREATE, P.INVOICE_VOID} & (wm | sr | rs))
    # Sales representatives do field work but no administration, purchasing or invoicing.
    assert {P.STOCKTAKE_RECORD, P.SALES_RECORD, P.REPLENISHMENT_REQUEST, P.TRANSFER_REQUEST} <= sr
    assert not ({P.USER_MANAGE, P.PURCHASING_MANAGE, P.INVOICE_READ, P.AUDIT_READ} & sr)
    # Reseller self-service: report sales, request replenishment / stock (approval needed), confirm own deliveries
    # and confirm stock-check shortages as sold or missing.
    assert rs == {P.CATALOGUE_READ, P.INVENTORY_READ, P.SALES_RECORD, P.REPLENISHMENT_READ, P.REPLENISHMENT_REQUEST,
                  P.TRANSFER_READ, P.INVOICE_READ, P.REPORT_READ, P.FEEDBACK_SUBMIT, P.STOCK_REQUEST_READ,
                  P.STOCK_REQUEST_CREATE, P.DELIVERY_CONFIRM, P.STOCKTAKE_CONFIRM}


@pytest.mark.parametrize("who, method, url, expected", [
    # Relationship Manager
    ("manager", "get", "/invoices", 200),
    ("manager", "get", "/resellers", 200),
    ("manager", "get", "/users", 200),
    ("manager", "get", "/audit-events", 200),
    # Warehouse Manager
    ("warehouse_op", "get", "/users", 403),
    ("warehouse_op", "get", "/audit-events", 403),
    ("warehouse_op", "get", "/purchasing/purchase-orders", 200),
    ("warehouse_op", "get", "/reports/warehouse-availability", 200),
    ("warehouse_op", "get", "/invoices", 403),
    # Sales Representative
    ("rep", "get", "/resellers", 200),
    ("rep", "get", "/stocktakes", 200),
    ("rep", "get", "/invoices", 403),
    ("rep", "get", "/users", 403),
    ("rep", "get", "/feedback", 403),
    # Reseller
    ("user_a", "get", "/reports/warehouse-availability", 403),
    ("user_a", "get", "/reports/demand-by-sku", 403),
    ("user_a", "get", "/reports/uninvoiced-sales", 403),
    ("user_a", "get", "/purchasing/purchase-orders", 403),
    ("user_a", "get", "/replenishment/pick-list", 403),
    ("user_a", "get", "/users", 403),
    ("user_a", "get", "/staff", 403),
    ("user_a", "get", "/audit-events", 403),
    ("user_a", "get", "/feedback", 403),
    ("user_a", "get", "/inventory/reconciliation", 403),
])
def test_role_access_is_enforced_by_the_api(world, who, method, url, expected):
    getattr(world.api(getattr(world, who)), method)(url, expected=expected)


def test_staff_writes_are_blocked_for_other_roles(world):
    po = {"supplier_name": "S", "warehouse_location_id": world.warehouse.id,
          "lines": [{"product_id": world.p1.id, "qty_ordered": 1}]}
    receipt = {"warehouse_location_id": world.warehouse.id, "lines": [{"product_id": world.p1.id, "qty_received": 1}]}
    for who in ("rep", "user_a"):
        api = world.api(getattr(world, who))
        api.post("/purchasing/purchase-orders", po, expected=403)
        api.post("/purchasing/receipts", receipt, expected=403)
    for who in ("warehouse_op", "manager"):   # the Relationship Manager can buy and receive too (P-028)
        world.api(getattr(world, who)).post("/purchasing/purchase-orders", po, expected=201)
        world.api(getattr(world, who)).post("/purchasing/receipts", receipt, expected=201)


def test_reseller_sees_only_own_balances_and_dashboard_has_no_warehouse(world):
    db = world.db
    set_stock(db, world.loc_a, world.p1, 4)
    set_stock(db, world.loc_b, world.p1, 9)
    set_stock(db, world.warehouse, world.p1, 50)
    db.commit()
    alpha = world.api(world.user_a)
    rows = alpha.get("/inventory/balances").json()
    assert {r["location_id"] for r in rows} == {world.loc_a.id}
    alpha.get("/inventory/balances", params={"location_id": world.warehouse.id})  # filtered, never warehouse rows
    assert all(r["location_type"] != "WAREHOUSE" for r in alpha.get("/inventory/balances",
                                                                     params={"location_type": "WAREHOUSE"}).json())
    dash = alpha.get("/reports/dashboard").json()
    assert dash["warehouse"] is None and dash["consignment"]["on_hand"] == 4


# ---------------------------------------------------------------------------
# Reseller self-service: replenishment requests
# ---------------------------------------------------------------------------


def test_reseller_requests_replenishment_for_own_location_only(world):
    db = world.db
    set_target(db, world.loc_a, world.p1, 6)
    set_target(db, world.loc_b, world.p1, 6)
    db.commit()
    alpha = world.api(world.user_a)
    body = {"location_id": world.loc_a.id, "product_id": world.p1.id, "quantity": 2, "reason": "Customer asked",
            "priority": "HIGH"}
    req = alpha.post("/replenishment/requests", body, expected=201).json()
    assert req["reseller_id"] == world.reseller_a.id and req["reason"] == "MANUAL"
    # Another reseller's location is "not found"; urgent priority and over-shortfall need staff.
    alpha.post("/replenishment/requests", {**body, "location_id": world.loc_b.id}, expected=404)
    alpha.post("/replenishment/requests", {**body, "priority": "URGENT"}, expected=422)
    alpha.post("/replenishment/requests", {**body, "quantity": 50}, expected=422)
    # Managing requests stays with dealership staff.
    alpha.post(f"/replenishment/requests/{req['id']}/allocate", {"quantity": 1}, expected=403)
    alpha.post(f"/replenishment/requests/{req['id']}/cancel", {"quantity": 1, "reason": "x"}, expected=403)
    alpha.post("/replenishment/generate-shortfalls", {}, expected=403)


# ---------------------------------------------------------------------------
# Passwords, feedback and reference documents
# ---------------------------------------------------------------------------


def test_admin_created_user_must_change_password(world, client):
    created = world.api(world.admin).post("/users", {"email": "new.rep@example.com", "full_name": "New Rep",
                                                     "password": "temporary-pass-1", "role": "SALES_REP"}).json()
    login = client.post("/api/auth/login", json={"email": "new.rep@example.com", "password": "temporary-pass-1"})
    assert login.status_code == 200 and login.json()["user"]["must_change_password"] is True
    assert login.json()["user"]["role_label"] == "Sales Representative"
    token = {"Authorization": f"Bearer {login.json()['access_token']}"}
    bad = client.post("/api/auth/password", json={"current_password": "nope", "new_password": "a-new-password"},
                      headers=token)
    assert bad.status_code == 422
    ok = client.post("/api/auth/password", json={"current_password": "temporary-pass-1",
                                                 "new_password": "my-own-password-2"}, headers=token)
    assert ok.status_code == 200 and ok.json()["must_change_password"] is False
    assert client.post("/api/auth/login", json={"email": "new.rep@example.com",
                                                "password": "my-own-password-2"}).status_code == 200
    assert world.db.get(User, created["id"]) is not None


def test_pilot_feedback_submit_and_review(world):
    for who in ("manager", "warehouse_op", "rep", "user_a"):
        world.api(getattr(world, who)).post("/feedback", {"page": "Dashboard", "feedback_type": "IMPROVEMENT",
                                                          "description": f"Note from {who}"}, expected=201)
    world.api(world.rep).post("/feedback", {"page": "X", "feedback_type": "RANT", "description": "abc"}, expected=422)
    world.api(world.warehouse_op).get("/feedback", expected=403)
    rows = world.api(world.manager).get("/feedback").json()
    assert len(rows) == 4 and {r["role"] for r in rows} == {"RELATIONSHIP_MANAGER", "WAREHOUSE_MANAGER",
                                                             "SALES_REP", "RESELLER"}
    assert all(r["user_name"] for r in rows)


@pytest.fixture
def reference_docs(tmp_path, monkeypatch):
    """A deployment's own reference documents (the product ships with none)."""
    (tmp_path / "price-list.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 20_000)
    (tmp_path / "manifest.json").write_text(json.dumps([{
        "id": "dealer-price-list-2026-07", "title": "Dealer Price List", "description": "Sample. Confidential.",
        "effective_date": "2026-07-07", "filename": "price-list.jpg", "media_type": "image/jpeg",
        "width": 1455, "height": 2000}]))
    monkeypatch.setattr(get_settings(), "reference_documents_dir", str(tmp_path))
    return tmp_path


def test_product_ships_without_reference_documents(world):
    assert world.api(world.manager).get("/reference-documents").json() == []
    world.api(world.manager).get("/reference-documents/dealer-price-list-2026-07/file", expected=404)


def test_reference_document_is_staff_only(world, reference_docs):
    docs = world.api(world.manager).get("/reference-documents").json()
    assert [d["id"] for d in docs] == ["dealer-price-list-2026-07"]
    assert docs[0]["effective_date"] == "2026-07-07"
    r = world.api(world.rep).get(docs[0]["url"].removeprefix("/api"))
    assert r.headers["content-type"] == "image/jpeg" and len(r.content) > 10_000
    assert world.api(world.user_a).get("/reference-documents").json() == []
    world.api(world.user_a).get("/reference-documents/dealer-price-list-2026-07/file", expected=404)
    world.api(world.manager).get("/reference-documents/unknown/file", expected=404)
    # The price list is a reference only: it never creates products.
    assert world.db.execute(select(func.count()).select_from(Product)).scalar_one() == 3


def test_unauthenticated_requests_are_rejected(client):
    for url in ("/api/reference-documents", "/api/reference-documents/dealer-price-list-2026-07/file",
                "/api/reports/dashboard", "/api/inventory/balances", "/api/feedback"):
        assert client.get(url).status_code == 401


# ---------------------------------------------------------------------------
# Controlled reset to a clean pilot state
# ---------------------------------------------------------------------------

PILOT_ENV = {
    "PILOT_RM_EMAIL": "rm@pilot.example.com", "PILOT_WM_EMAIL": "wm@pilot.example.com",
    "PILOT_SR_EMAIL": "sr@pilot.example.com", "PILOT_RESELLER_EMAIL": "reseller@pilot.example.com",
    "PILOT_RESELLER_BUSINESS_NAME": "Pilot Reseller Ltd", "PILOT_RESELLER_ACCOUNT_REF": "PR001",
    "PILOT_WM_PASSWORD": "warehouse-pass-1",
}


def _args(**kw):
    return argparse.Namespace(confirm=kw.get("confirm"), dry_run=kw.get("dry_run", False),
                              allow_production=kw.get("allow_production", False))


def test_reset_requires_explicit_confirmation(world, monkeypatch):
    from scripts import reset_to_pilot

    for k, v in PILOT_ENV.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(SystemExit, match="RESET-PILOT"):
        reset_to_pilot.reset(_args(confirm="yes"))
    before = reset_to_pilot.reset(_args(dry_run=True))
    assert before["Products"] == 3 and before["Dealers"] == 3   # dry run changes nothing


def test_reset_refuses_production_without_extra_confirmation(world, monkeypatch):
    from scripts import reset_to_pilot

    class Prod:
        app_env = "production"

    monkeypatch.setattr(reset_to_pilot, "get_settings", lambda: Prod())
    with pytest.raises(SystemExit, match="production"):
        reset_to_pilot.reset(_args(confirm="RESET-PILOT"))
    with pytest.raises(SystemExit, match="production"):
        reset_to_pilot.reset(_args(confirm="RESET-PILOT", allow_production=True))   # env flag still missing


def test_reset_requires_staff_emails(world, monkeypatch):
    from scripts import reset_to_pilot

    for k in ("PILOT_RM_EMAIL", "PILOT_WM_EMAIL", "PILOT_SR_EMAIL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SystemExit, match="PILOT_RM_EMAIL"):
        reset_to_pilot.reset(_args(confirm="RESET-PILOT"))
    assert world.db.execute(select(func.count()).select_from(Product)).scalar_one() == 3   # nothing deleted


def test_reset_produces_clean_pilot_state(world, monkeypatch, db, capsys, client):
    from scripts import reset_to_pilot

    set_stock(world.db, world.loc_a, world.p1, 5)
    world.db.commit()
    for k, v in PILOT_ENV.items():
        monkeypatch.setenv(k, v)
    after = reset_to_pilot.reset(_args(confirm="RESET-PILOT"))
    out = capsys.readouterr().out
    db.expire_all()

    for label in ("Products", "Consignment targets", "Customer prices", "Stock balance rows", "Ledger transactions",
                  "Stock reservations", "Purchase orders", "Goods receipts", "Sales", "Stocktakes",
                  "Replenishment requests", "Deliveries", "Transfers", "Invoices", "Pilot feedback"):
        assert after[label] == 0, label
    assert after["Users"] == 4 and after["Dealers"] == 1 and after["Tax rates"] == 1
    users = db.execute(select(User).order_by(User.id)).scalars().all()
    assert [u.role for u in users] == [Role.RELATIONSHIP_MANAGER, Role.WAREHOUSE_MANAGER, Role.SALES_REP, Role.RESELLER]
    assert all(u.must_change_password for u in users)
    assert db.execute(select(Reseller)).scalar_one().account_ref == "PR001"
    assert db.execute(select(TaxRate)).scalar_one().is_default
    types = sorted(loc.type.value for loc in db.execute(select(Location)).scalars())
    assert types.count("WAREHOUSE") == 1 and types.count("CONSIGNMENT") == 1 and len(types) == 8  # + 6 system
    assert db.execute(select(Location).where(Location.type == LocationType.WAREHOUSE)).scalar_one().is_default_warehouse
    # Passwords: generated ones are printed once; supplied ones are never echoed.
    assert "warehouse-pass-1" not in out and "(from environment variable)" in out
    # The supplied password works; the account is flagged to change it.
    login = client.post("/api/auth/login", json={"email": "wm@pilot.example.com", "password": "warehouse-pass-1"})
    assert login.status_code == 200 and login.json()["user"]["must_change_password"] is True
    # Dashboards start genuinely empty (no fabricated numbers).
    token = {"Authorization": f"Bearer {login.json()['access_token']}"}
    dash = client.get("/api/reports/dashboard", headers=token).json()
    assert dash["warehouse"] == {"on_hand": 0, "reserved": 0, "blocked": 0, "available": 0}
    assert dash["consignment"]["on_hand"] == 0 and dash["backorders"]["requests"] == 0
    assert dash["sales_awaiting_invoicing"]["qty"] == 0 and dash["transfers_in_progress"]["count"] == 0


def test_reset_without_reseller_details_creates_three_staff_accounts(world, monkeypatch, db):
    from scripts import reset_to_pilot

    for k, v in PILOT_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("PILOT_RESELLER_BUSINESS_NAME")
    after = reset_to_pilot.reset(_args(confirm="RESET-PILOT"))
    assert after["Users"] == 3 and after["Dealers"] == 0


def test_test_suite_refuses_non_test_databases():
    from tests import conftest

    assert conftest.is_disposable_test_url("postgresql+psycopg://u:p@localhost:5432/tyreworld_test")
    assert not conftest.is_disposable_test_url("postgresql+psycopg://u:p@ep-x.neon.tech/neondb?sslmode=require")
    assert not conftest.is_disposable_test_url("postgresql+psycopg://u:p@localhost:5432/tyreworld")


def test_relationship_manager_can_add_but_not_edit_products(world):
    body = {"sku": "RM-NEW-1", "brand": "CEAT", "pattern": "EcoDrive", "width": 195, "aspect_ratio": 65,
            "rim_diameter": "15", "load_index": "91", "speed_rating": "H", "list_price": "79.00"}
    created = world.api(world.manager).post("/products", body, expected=201).json()
    assert created["sku"] == "RM-NEW-1"
    # Since P-028 the Relationship Manager can also edit existing products.
    assert world.api(world.manager).patch(f"/products/{created['id']}", {"pattern": "EcoDrive 2"}).json()["pattern"] \
        == "EcoDrive 2"
    world.api(world.rep).post("/products", {**body, "sku": "SR-NEW-1"}, expected=403)
    world.api(world.warehouse_op).post("/products", {**body, "sku": "WM-NEW-1"}, expected=201)
