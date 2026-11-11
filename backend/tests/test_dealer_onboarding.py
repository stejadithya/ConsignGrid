"""Release 1.11 — adding a dealer (findings 8–14): automatic account reference, mandatory details, several shops,
the dealer's login, initial stock from Excel and a copy of the signed agreement."""

import base64
import io

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import select, text

from app.modules.audit.models import AuditEvent
from app.modules.customers.models import Reseller
from app.modules.customers.refs import city_code, dealer_code
from app.modules.identity.models import User

pytestmark = pytest.mark.usefixtures("ledger_balanced")   # every test ends with the ledger reconciled


def _dealer(world, name="Akash Kumar Tyres", city="Auckland", **extra):
    body = {"business_name": name, "contact_name": "Akash Kumar", "email": f"{name.split()[0].lower()}@example.com",
            "phone": "09 555 0101", "billing_address": "1 Queen Street, Auckland", "sales_rep_user_id": world.rep.id,
            "locations": [{"name": "Main shop", "address_line1": "1 Queen Street", "city": city}]}
    body.update(extra)
    return body


def _create(world, expected=201, **kw):
    return world.api(world.manager).post("/resellers", _dealer(world, **kw), expected=expected).json()


# --- Account reference (finding 8, D4) -----------------------------------------------------------------------------

@pytest.mark.parametrize("name, code", [("Akash Kumar Tyres", "AKT"), ("Tyre World Ltd", "TYW"), ("Bridgestone", "BRI"),
                                        ("The Tyre & Wheel Company", "TYW"), ("NZ Tyres Limited", "TYR")])
def test_dealer_code_examples(name, code):
    assert dealer_code(name) == code


def test_city_code_examples():
    assert (city_code("Auckland"), city_code("Wellington"), city_code("Ōtaki")) == ("AUC", "WEL", "TAK")


def test_references_are_generated_in_sequence_and_never_collide(world):
    assert world.api(world.manager).get("/resellers/account-ref-preview",
                                        params={"business_name": "Akash Kumar Tyres", "city": "Auckland"}).json() == \
        {"account_ref": "AKT-AUC-001", "hint": "Final reference is confirmed when you save"}
    first = _create(world)
    second = _create(world, email="second@example.com")
    assert (first["account_ref"], second["account_ref"]) == ("AKT-AUC-001", "AKT-AUC-002")
    # A reference already in use is skipped, even if the sequence was cleared (e.g. by the UAT clean-up).
    world.db.add(Reseller(account_ref="AKT-AUC-007", business_name="Older dealer"))
    world.db.execute(text("DELETE FROM number_sequences WHERE prefix = 'AKTAUC'"))
    world.db.commit()
    assert _create(world, email="third@example.com")["account_ref"] == "AKT-AUC-008"
    # An explicit reference is still accepted and kept as given (existing dealers never change).
    assert _create(world, email="x@example.com", account_ref="leg-1")["account_ref"] == "LEG-1"


# --- Mandatory details (finding 9) ---------------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["contact_name", "email", "phone", "billing_address", "sales_rep_user_id", "locations"])
def test_each_mandatory_field_is_required(world, field):
    body = _dealer(world)
    body.pop(field)
    world.api(world.manager).post("/resellers", body, expected=422)


@pytest.mark.parametrize("shop_field", ["name", "address_line1", "city"])
def test_each_shop_field_is_required(world, shop_field):
    body = _dealer(world)
    body["locations"][0][shop_field] = "  "
    world.api(world.manager).post("/resellers", body, expected=422)


def test_details_cannot_be_blanked_and_rep_must_be_a_sales_rep(world):
    r = _create(world)
    rm = world.api(world.manager)
    for field in ("contact_name", "phone", "billing_address"):
        rm.patch(f"/resellers/{r['id']}", {field: ""}, expected=422)
    rm.patch(f"/resellers/{r['id']}", {"email": None}, expected=422)
    rm.patch(f"/resellers/{r['id']}", {"sales_rep_user_id": world.warehouse_op.id}, expected=422)
    assert rm.patch(f"/resellers/{r['id']}", {"phone": "09 555 0202"}).json()["phone"] == "09 555 0202"
    reps = rm.get("/staff", params={"role": "SALES_REP"}).json()
    assert {u["role"] for u in reps} == {"SALES_REP"}


# --- Several shops (finding 11) ------------------------------------------------------------------------------------

def test_two_shops_get_generated_codes_and_a_third_can_be_added(world):
    shops = [{"name": "North", "address_line1": "1 North Rd", "city": "Auckland"},
             {"name": "South", "address_line1": "9 South Rd", "city": "Manukau", "postcode": "2104", "contact_phone": "09 1"}]
    r = _create(world, locations=shops)
    ref = r["account_ref"]
    assert [(loc["code"], loc["city"]) for loc in r["locations"]] == [(f"{ref}-01", "Auckland"), (f"{ref}-02", "Manukau")]
    third = world.api(world.manager).post(f"/resellers/{r['id']}/locations",
                                          {"name": "East", "address_line1": "5 East Rd", "city": "Auckland"}).json()
    assert third["code"] == f"{ref}-03"
    world.api(world.manager).post(f"/resellers/{r['id']}/locations", {"name": "No city", "address_line1": "x"},
                                  expected=422)


# --- The dealer's login (finding 12, D7) ---------------------------------------------------------------------------

def test_login_is_created_with_the_dealer_and_shown_once(world):
    r = _create(world, email="Owner@Akash.Example.com", create_login=True)
    login = r["login"]
    assert login["email"] == "owner@akash.example.com" and len(login["temporary_password"]) == 12
    assert not set(login["temporary_password"]) & set("0O1lI")
    user = world.db.execute(select(User).where(User.email == "owner@akash.example.com")).scalar_one()
    assert (user.role, user.reseller_id, user.must_change_password, user.full_name) == \
        ("RESELLER", r["id"], True, "Akash Kumar")
    resp = world.client.post("/api/auth/login", json={"email": login["email"], "password": login["temporary_password"]})
    assert resp.status_code == 200
    # Never stored in the change history; never repeated.
    for e in world.db.execute(select(AuditEvent)).scalars():
        assert login["temporary_password"] not in f"{e.summary} {e.details}"
    assert world.api(world.manager).get(f"/resellers/{r['id']}").json()["login"] is None


def test_duplicate_login_email_creates_nothing(world):
    before = world.db.execute(select(Reseller)).scalars().all()
    body = _dealer(world, email=world.user_a.email.upper(), create_login=True)
    resp = world.api(world.manager).post("/resellers", body, expected=409).json()
    assert "already exists" in resp["detail"]
    world.db.expire_all()
    assert len(world.db.execute(select(Reseller)).scalars().all()) == len(before)


def test_no_login_unless_asked(world):
    r = _create(world)
    assert r["login"] is None
    assert world.db.execute(select(User).where(User.email == "akash@example.com")).scalar_one_or_none() is None


# --- Initial stock from Excel (finding 13) -------------------------------------------------------------------------

def _xlsx(rows):
    wb = Workbook()
    for row in rows:
        wb.active.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


def test_initial_stock_excel_check_then_commit(world):
    shops = [{"name": "North", "address_line1": "1 North Rd", "city": "Auckland"},
             {"name": "South", "address_line1": "9 South Rd", "city": "Auckland"}]
    r = _create(world, locations=shops)
    north, south = (loc["code"] for loc in r["locations"])
    world.p3.is_active = False
    world.db.commit()
    rm = world.api(world.manager)
    tpl = rm.get("/resellers/initial-stock/template")
    assert [c.value for c in load_workbook(io.BytesIO(tpl.content)).active[1]][:3] == ["SKU Code", "Quantity", "Shop code"]
    bad = _xlsx([["SKU Code", "Quantity", "Shop code"], ["TYR-001", 4, north], ["NOPE", 1, north], ["TYR-003", 2, north],
                 ["TYR-002", 0, south], ["TYR-001", 1, north], ["TYR-002", 3, "ELSEWHERE"], ["TYR-002", 3, None]])
    check = rm.post(f"/resellers/{r['id']}/initial-stock/import", {"content_base64": bad}).json()
    errors = {x["row"]: " ".join(x["errors"]) for x in check["rows"] if x["errors"]}
    assert "Unknown SKU NOPE" in errors[3] and "inactive" in errors[4] and "whole number" in errors[5]
    assert "more than once" in errors[6] and "Unknown shop" in errors[7] and "Shop code is needed" in errors[8]
    rm.post(f"/resellers/{r['id']}/initial-stock/import", {"content_base64": bad, "commit": True}, expected=422)
    good = _xlsx([["SKU Code", "Quantity", "Shop code"], ["TYR-001", 4, north], ["TYR-002", 2, north], ["TYR-001", 3, south]])
    done = rm.post(f"/resellers/{r['id']}/initial-stock/import", {"content_base64": good, "commit": True}).json()
    assert done["summary"] == {"total": 3, "valid": 3, "errors": 0, "units": 9} and len(done["posted"]) == 2
    balances = {(b["location_code"], b["sku"]): b["on_hand"] for b in rm.get("/inventory/balances").json()
                if b["location_code"] in (north, south)}
    assert balances == {(north, "TYR-001"): 4, (north, "TYR-002"): 2, (south, "TYR-001"): 3}
    assert world.api(world.warehouse_op).get("/inventory/reconciliation").json()["balanced"] is True
    # A dealer cannot import, and dealers' shops are private.
    world.api(world.user_a).post(f"/resellers/{r['id']}/initial-stock/import", {"content_base64": good}, expected=403)


def test_single_shop_needs_no_shop_code(world):
    r = _create(world)
    done = world.api(world.manager).post(f"/resellers/{r['id']}/initial-stock/import", {
        "content_base64": _xlsx([["SKU Code", "Quantity"], ["TYR-002", 5]]), "commit": True}).json()
    assert done["posted"][0]["units"] == 5


# --- Agreement copy (finding 14, D8) -------------------------------------------------------------------------------

PDF = base64.b64encode(b"%PDF-1.4\n% test agreement\n").decode()


def test_agreement_copy_upload_types_size_and_isolation(world):
    rm = world.api(world.manager)
    rid = world.reseller_a.id
    f = rm.post(f"/resellers/{rid}/agreement-files", {"filename": "signed.pdf", "content_base64": PDF}, expected=201).json()
    assert (f["content_type"], f["filename"]) == ("application/pdf", "signed.pdf")
    rm.post(f"/resellers/{rid}/agreement-files", {"filename": "notes.txt", "content_base64": base64.b64encode(b"hello").decode()},
            expected=422)
    big = base64.b64encode(b"%PDF" + b"0" * (5 * 1024 * 1024)).decode()
    rm.post(f"/resellers/{rid}/agreement-files", {"filename": "big.pdf", "content_base64": big}, expected=422)
    # The dealer sees their own copy; another dealer cannot; dealers cannot upload.
    alpha, bravo = world.api(world.user_a), world.api(world.user_b)
    assert [x["id"] for x in alpha.get(f"/resellers/{rid}/agreement-files").json()] == [f["id"]]
    assert alpha.get(f"/resellers/{rid}/agreement-files/{f['id']}").content.startswith(b"%PDF")
    bravo.get(f"/resellers/{rid}/agreement-files", expected=404)
    bravo.get(f"/resellers/{rid}/agreement-files/{f['id']}", expected=404)
    alpha.post(f"/resellers/{rid}/agreement-files", {"filename": "x.pdf", "content_base64": PDF}, expected=403)
    # Removing hides it.
    world.client.request("DELETE", f"/api/resellers/{rid}/agreement-files/{f['id']}", headers=rm.headers)
    assert rm.get(f"/resellers/{rid}/agreement-files").json() == []
    rm.get(f"/resellers/{rid}/agreement-files/{f['id']}", expected=404)
