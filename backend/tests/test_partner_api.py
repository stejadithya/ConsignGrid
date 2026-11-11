"""Website stock API (Stage A): API keys and warehouse stock status bands (IN_STOCK / LOW / OUT)."""

import hashlib

import pytest
from sqlalchemy import select

from app.core.permissions import Role
from app.modules.audit.models import AuditEvent
from app.modules.inventory.models import ReservationPurpose, TxnType
from app.modules.inventory.service import Ledger, Ref
from app.modules.partner.models import PartnerApiKey
from tests.factories import make_product, make_user, set_stock

pytestmark = pytest.mark.usefixtures("ledger_balanced")


@pytest.fixture
def administrator(world):
    u = make_user(world.db, Role.ADMINISTRATOR, "root@example.com", name="Root Admin")
    world.db.commit()
    return u


@pytest.fixture
def key(world, administrator):
    return world.api(administrator).post("/partner-keys", {"name": "Customer website"}).json()["key"]


def stock(client, key, path="/partner/v1/stock", **kw):
    return client.get(f"/api{path}", headers={"X-API-Key": key} if key is not None else {}, **kw)


def statuses(client, key, **kw):
    return {i["sku"]: i["status"] for i in stock(client, key, **kw).json()["items"]}


# --- Keys ----------------------------------------------------------------------------------------------------------

def test_key_is_shown_once_and_stored_only_as_a_hash(world, administrator):
    api = world.api(administrator)
    created = api.post("/partner-keys", {"name": "Customer website"}).json()
    raw = created["key"]
    assert raw.startswith("tg_live_") and len(raw) > 40
    assert created["key_prefix"] == raw[:12]
    row = world.db.execute(select(PartnerApiKey)).scalar_one()
    assert row.key_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in (row.key_hash, row.key_prefix)
    listed = api.get("/partner-keys").json()
    assert [k["name"] for k in listed] == ["Customer website"]
    assert "key" not in listed[0] and listed[0]["created_by"] == "Root Admin"
    actions = world.db.execute(select(AuditEvent.action)).scalars().all()
    assert "partner_key.create" in actions


def test_only_administrators_manage_keys(world, administrator):
    for user in (world.manager, world.warehouse_op, world.rep, world.user_a):
        world.api(user).get("/partner-keys", expected=403)
        world.api(user).post("/partner-keys", {"name": "Sneaky"}, expected=403)
    world.api(administrator).get("/partner-keys")


def test_missing_wrong_and_revoked_keys_are_refused(world, administrator, key, client):
    assert stock(client, None).status_code == 401
    assert stock(client, "tg_live_not-a-real-key").status_code == 401
    assert stock(client, "something-else").json()["code"] == "invalid_api_key"
    # A staff login is not a key: the website API ignores session tokens.
    staff = world.api(world.manager)
    assert client.get("/api/partner/v1/stock", headers=staff.headers).status_code == 401
    assert stock(client, key).status_code == 200
    key_id = world.api(administrator).get("/partner-keys").json()[0]["id"]
    world.api(administrator).post(f"/partner-keys/{key_id}/revoke")
    assert stock(client, key).status_code == 401
    world.api(administrator).post(f"/partner-keys/{key_id}/revoke", expected=409)
    assert "partner_key.revoke" in world.db.execute(select(AuditEvent.action)).scalars().all()


def test_a_new_key_works_alongside_the_old_one_for_rotation(world, administrator, key, client):
    second = world.api(administrator).post("/partner-keys", {"name": "Customer website (new)"}).json()["key"]
    assert stock(client, key).status_code == 200
    assert stock(client, second).status_code == 200


def test_last_used_is_recorded(world, key, client):
    assert world.db.execute(select(PartnerApiKey.last_used_at)).scalar_one() is None
    stock(client, key)
    world.db.expire_all()
    assert world.db.execute(select(PartnerApiKey.last_used_at)).scalar_one() is not None


# --- Stock status --------------------------------------------------------------------------------------------------

def test_bands_follow_warehouse_available_stock(world, key, client):
    db, wh = world.db, world.warehouse
    set_stock(db, wh, world.p1, 5)          # 5 → IN_STOCK
    set_stock(db, wh, world.p2, 4)          # 4 → LOW (the threshold)
    set_stock(db, wh, world.p3, 1)          # 1 → LOW
    p4 = make_product(db, "TYR-004")         # none → OUT
    db.commit()
    assert statuses(client, key) == {"TYR-001": "IN_STOCK", "TYR-002": "LOW", "TYR-003": "LOW", p4.sku: "OUT"}


def test_reserved_and_blocked_stock_is_not_sellable(world, key, client):
    db, wh = world.db, world.warehouse
    set_stock(db, wh, world.p1, 6)
    ledger = Ledger(db, TxnType.RESERVATION, actor_id=world.warehouse_op.id, ref=Ref("test", None, "TEST"))
    ledger.reserve(wh, world.p1.id, 1, ReservationPurpose.REPLENISHMENT)   # 5 available → IN_STOCK
    db.commit()
    assert statuses(client, key)["TYR-001"] == "IN_STOCK"
    Ledger(db, TxnType.BLOCK, actor_id=world.warehouse_op.id, ref=Ref("test", None, "TEST")).block(wh, world.p1.id, 1)
    db.commit()                                                              # 4 available → LOW
    assert statuses(client, key)["TYR-001"] == "LOW"
    Ledger(db, TxnType.BLOCK, actor_id=world.warehouse_op.id, ref=Ref("test", None, "TEST")).block(wh, world.p1.id, 4)
    db.commit()                                                              # 0 available → OUT
    assert statuses(client, key)["TYR-001"] == "OUT"


def test_dealer_stock_does_not_count(world, key, client):
    set_stock(world.db, world.loc_a, world.p1, 20)
    world.db.commit()
    assert statuses(client, key)["TYR-001"] == "OUT"


def test_inactive_products_leave_the_list_and_read_out_when_asked_for(world, key, client):
    set_stock(world.db, world.warehouse, world.p1, 10)
    world.p1.is_active = False
    world.db.commit()
    assert "TYR-001" not in statuses(client, key)
    assert stock(client, key, "/partner/v1/stock/TYR-001").json()["status"] == "OUT"
    assert statuses(client, key, params={"sku": ["TYR-001"]}) == {"TYR-001": "OUT"}


def test_filter_single_sku_unknown_and_limit(world, key, client):
    set_stock(world.db, world.warehouse, world.p2, 9)
    world.db.commit()
    r = stock(client, key, params={"sku": ["TYR-002", "NOPE-1", "TYR-002"]}).json()
    assert [i["sku"] for i in r["items"]] == ["TYR-002"] and r["unknown_skus"] == ["NOPE-1"]
    one = stock(client, key, "/partner/v1/stock/TYR-002")
    assert one.status_code == 200
    assert one.json() == {"sku": "TYR-002", "name": "Bridgestone Turanza T005", "size": "225/45R17 94W", "status": "IN_STOCK"}
    assert stock(client, key, "/partner/v1/stock/NOPE-1").status_code == 404
    assert stock(client, key, params={"sku": [f"S{i}" for i in range(101)]}).status_code == 422


def test_response_holds_status_bands_only(world, key, client):
    set_stock(world.db, world.warehouse, world.p1, 3)
    set_stock(world.db, world.loc_a, world.p1, 2)
    world.db.commit()
    r = stock(client, key)
    assert r.headers["cache-control"] == "private, max-age=60"
    body = r.json()
    assert set(body) == {"generated_at", "items", "unknown_skus"}
    for item in body["items"]:
        assert set(item) == {"sku", "name", "size", "status"}
        assert item["status"] in {"IN_STOCK", "LOW", "OUT"}
    text = r.text
    for secret in ("WH-MAIN", "RA-MAIN", "Alpha", "180.00", "120.00", "on_hand", "available"):
        assert secret not in text
