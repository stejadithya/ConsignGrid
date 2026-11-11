"""Excel product master import, the blank template, and the Administrator super user."""

import base64
import io
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select

from app.core.permissions import ROLE_PERMISSIONS, P, Role
from app.modules.audit.models import AuditEvent
from app.modules.catalogue.models import Product
from app.modules.identity.models import User
from app.modules.inventory.models import StockBalance
from tests.factories import make_user

# A fictional sample catalogue (no real brand, SKUs or prices) with the same layout as a supplier price list:
# title rows, 38 valid tyres and one row whose SKU and size are unreadable.
PRICE_LIST = Path(__file__).resolve().parents[1] / "data" / "products" / "sample-tyre-catalogue.xlsx"


def _xlsx(rows: list[list], title_rows: int = 0) -> str:
    wb = Workbook()
    ws = wb.active
    for _ in range(title_rows):
        ws.append(["Some title"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


def _import(api, content: str, commit: bool, expected=200):
    return api.post("/products/import", {"filename": "test.xlsx", "content_base64": content, "commit": commit},
                    expected=expected).json()


HEADER = ["SKU Code", "SKU Description", "Dealer Price (excl. GST & Stewardship)", "RRP (incl. GST but excl. Stewardship)"]


def test_sample_catalogue_imports_38_skus_and_rejects_the_unreadable_row(world):
    api = world.api(world.warehouse_op)
    content = base64.b64encode(PRICE_LIST.read_bytes()).decode()
    check = _import(api, content, commit=False)
    assert check["summary"] == {"create": 38, "update": 0, "unchanged": 0, "error": 1, "total": 39}
    assert world.db.execute(select(func.count()).select_from(Product)).scalar_one() == 3   # check changes nothing
    bad = [r for r in check["rows"] if r["action"] == "error"]
    assert len(bad) == 1 and "not valid" in " ".join(bad[0]["errors"]) and "size" in " ".join(bad[0]["errors"]).lower()
    commercial = next(r for r in check["rows"] if r["sku"] == "710099")
    assert commercial["size"] == "195/80R15" and commercial["load_index"] == "106/104" and commercial["warnings"]

    done = _import(api, content, commit=True)
    assert done["result"] == {"created": 38, "updated": 0, "unchanged": 0, "skipped": 1}
    world.db.expire_all()
    p = world.db.execute(select(Product).where(Product.sku == "710001")).scalar_one()
    assert (p.brand, p.pattern, p.width, p.aspect_ratio, p.rim_diameter, p.load_index, p.speed_rating) == \
        ("NORDWAY", "TRAILSURE SUV AS", 225, 65, Decimal("17"), "102", "H")
    # Prices in the file are ignored: they are managed in Xero (D2).
    assert check["notes"] == ["Price columns are ignored: prices are managed in Xero"]
    assert (p.list_price, p.rrp, p.description) == (None, None, "225/65R17 TRAILSURE SUV AS 102H TL NORDWAY")
    # Products only: no stock is created by an import.
    assert world.db.execute(select(func.count()).select_from(StockBalance)).scalar_one() == 0
    assert world.db.execute(select(AuditEvent).where(AuditEvent.action == "product.import")).scalars().one()

    # Importing the same file again changes nothing.
    again = _import(api, content, commit=False)
    assert again["summary"]["unchanged"] == 38 and again["summary"]["create"] == 0


def test_reimport_updates_details_but_never_prices_or_the_size(world):
    api = world.api(world.manager)                 # Relationship Manager may import
    _import(api, _xlsx([HEADER, ["900001", "205/55R16 ECODRIVE TL 91H CEAT", 89, 225]]), commit=True)
    res = _import(api, _xlsx([HEADER, ["900001", "205/60R16 ECODRIVE TL 91H CEAT", 95, 239]]), commit=True)
    row = res["rows"][0]
    assert row["action"] == "update" and any("Description" in c for c in row["changes"])
    assert not any("price" in c.lower() or "rrp" in c.lower() for c in row["changes"])
    assert any("not changed" in w for w in row["warnings"])
    world.db.expire_all()
    p = world.db.execute(select(Product).where(Product.sku == "900001")).scalar_one()
    assert (p.aspect_ratio, p.list_price, p.rrp) == (55, None, None)


def test_template_columns_override_the_description_and_errors_are_reported(world):
    api = world.api(world.warehouse_op)
    header = ["SKU Code", "SKU Description", "Dealer Price (excl. GST & Stewardship)", "RRP (incl. GST, excl. Stewardship)",
              "Brand", "Pattern", "Width (mm)", "Aspect Ratio", "Rim Diameter (in)", "Load Index", "Speed Rating",
              "Barcode", "Cost Price (excl. GST)", "Active (Y/N)"]
    rows = [header,
            ["A-1", "Custom tyre", 100, 200, "Acme", "Grip", 215, 60, 16, "99", "v", "9400000000001", 60, "N"],
            ["A-1", "205/55R16 ECODRIVE TL 91H CEAT", 89, 225, None, None, None, None, None, None, None, None, None, None],
            ["", "205/55R16 ECODRIVE TL 91H CEAT", 89, 225, None, None, None, None, None, None, None, None, None, None],
            ["A-3", "205/55R16 ECODRIVE TL 91H CEAT", "abc", None, None, None, None, None, None, None, None, None, None, None],
            ["A 4", "205/55R16 ECODRIVE TL 91H CEAT", 89, None, None, None, None, None, None, None, None, None, None, None],
            ["A-5", "Mystery tyre", 50, None, None, None, None, None, None, None, None, None, None, None]]
    res = _import(api, _xlsx(rows, title_rows=2), commit=True)
    by_row = {r["row"]: r for r in res["rows"]}
    # A text "price" is no longer an error: price columns are ignored (D2).
    assert res["header_row"] == 3 and res["summary"]["create"] == 2 and res["summary"]["error"] == 4
    assert "more than once" in by_row[5]["errors"][0]
    assert "missing" in by_row[6]["errors"][0]
    assert by_row[7]["action"] == "create" and not by_row[7]["errors"]
    assert any("not valid" in e for e in by_row[8]["errors"])
    assert any("size not found" in e.lower() for e in by_row[9]["errors"])
    world.db.expire_all()
    p = world.db.execute(select(Product).where(Product.sku == "A-1")).scalar_one()
    assert (p.brand, p.pattern, p.width, p.speed_rating, p.barcode, p.cost_price, p.is_active) == \
        ("Acme", "Grip", 215, "V", "9400000000001", None, False)


def test_import_rejects_unreadable_files_and_missing_headers(world):
    api = world.api(world.warehouse_op)
    r = _import(api, base64.b64encode(b"not a spreadsheet").decode(), commit=False, expected=422)
    assert "Excel" in r["detail"]
    r = _import(api, _xlsx([["Code", "Name"], ["1", "x"]]), commit=False, expected=422)
    assert "header" in r["detail"].lower()


def test_import_permissions(world):
    content = _xlsx([HEADER, ["900002", "205/55R16 ECODRIVE TL 91H CEAT", 89, 225]])
    for who in ("rep", "user_a"):
        _import(world.api(getattr(world, who)), content, commit=False, expected=403)
        world.api(getattr(world, who)).get("/products/import/template", expected=403)
    for who in ("manager", "warehouse_op"):
        _import(world.api(getattr(world, who)), content, commit=False)
    assert {P.CATALOGUE_IMPORT} <= ROLE_PERMISSIONS[Role.RELATIONSHIP_MANAGER] & ROLE_PERMISSIONS[Role.WAREHOUSE_MANAGER]


def test_blank_template_downloads_and_round_trips(world):
    r = world.api(world.manager).get("/products/import/template")
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["SKUs", "Instructions"]
    headers = [c.value for c in wb["SKUs"][1]]
    # No price columns (D2).
    assert headers == ["SKU Code", "SKU Description", "Brand", "Pattern", "Width (mm)", "Aspect Ratio",
                       "Rim Diameter (in)", "Load Index", "Speed Rating", "Barcode", "Active (Y/N)"]
    ws = wb["SKUs"]
    ws.append(["T-100", "215/55R17 SECURADRIVE TL 94W CEAT"])
    buf = io.BytesIO()
    wb.save(buf)
    res = _import(world.api(world.manager), base64.b64encode(buf.getvalue()).decode(), commit=False)
    assert res["summary"] == {"create": 1, "update": 0, "unchanged": 0, "error": 0, "total": 1}


# ---------------------------------------------------------------------------
# Administrator (super user)
# ---------------------------------------------------------------------------


def test_administrator_has_every_permission(world, db):
    admin = make_user(db, Role.ADMINISTRATOR, "super@example.com", name="Sam Super")
    db.commit()
    assert ROLE_PERMISSIONS[Role.ADMINISTRATOR] == frozenset(P)
    api = world.api(admin)
    for url in ("/users", "/invoices", "/audit-events", "/feedback", "/purchasing/purchase-orders",
                "/reports/warehouse-availability", "/products/import/template"):
        api.get(url)
    me = api.get("/auth/me").json()
    assert me["role_label"] == "Administrator" and "catalogue.import" in me["permissions"]


def test_only_administrators_manage_administrator_accounts(world, db):
    admin = make_user(db, Role.ADMINISTRATOR, "super@example.com", name="Sam Super")
    db.commit()
    wm = world.api(world.warehouse_op)            # Warehouse Manager can manage users, but not administrators
    data = {"email": "x@example.com", "full_name": "X", "password": "long-enough-pw", "role": "ADMINISTRATOR"}
    wm.post("/users", data, expected=403)
    wm.patch(f"/users/{world.rep.id}", {"role": "ADMINISTRATOR"}, expected=403)
    wm.patch(f"/users/{admin.id}", {"password": "hijacked-password"}, expected=403)
    created = world.api(admin).post("/users", data, expected=201).json()
    assert created["role"] == "ADMINISTRATOR"


def test_create_admin_script_is_safe_and_idempotent(world, monkeypatch, db, client):
    from scripts import create_admin

    monkeypatch.setenv("PILOT_ADMIN_EMAIL", "Boss@Example.com")
    monkeypatch.setenv("PILOT_ADMIN_PASSWORD", "default-admin-1")
    products_before = db.execute(select(func.count()).select_from(Product)).scalar_one()
    create_admin.create_admin()
    create_admin.create_admin()                   # second run keeps a single account
    db.expire_all()
    admins = db.execute(select(User).where(User.email == "boss@example.com")).scalars().all()
    assert len(admins) == 1 and admins[0].role == Role.ADMINISTRATOR
    assert db.execute(select(func.count()).select_from(Product)).scalar_one() == products_before  # data untouched
    login = client.post("/api/auth/login", json={"email": "boss@example.com", "password": "default-admin-1"})
    assert login.status_code == 200
    body = login.json()["user"]
    assert body["role"] == "ADMINISTRATOR" and body["must_change_password"] is True

    monkeypatch.setenv("PILOT_ADMIN_PASSWORD", "short")
    with pytest.raises(SystemExit, match="10 characters"):
        create_admin.create_admin()
    monkeypatch.delenv("PILOT_ADMIN_PASSWORD")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(SystemExit, match="PILOT_ADMIN_PASSWORD"):
        create_admin.create_admin()
