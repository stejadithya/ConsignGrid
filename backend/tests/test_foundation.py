"""Phase 1: authentication, role-based access, catalogue, resellers, locations, allocations."""

from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.catalogue.models import Product
from app.modules.consignment.models import AllocationChange


def test_login_sets_cookie_and_returns_permissions(world):
    r = world.client.post("/api/auth/login", json={"email": "rep@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "SALES_REP"
    assert "sales.record" in body["user"]["permissions"]
    assert "inventory.adjust" not in body["user"]["permissions"]
    assert "session" in r.cookies
    # The cookie alone authenticates subsequent requests.
    me = world.client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "rep@example.com"


def test_login_rejects_bad_password_and_unknown_user(world):
    assert world.client.post("/api/auth/login", json={"email": "rep@example.com", "password": "nope"}).status_code == 401
    assert world.client.post("/api/auth/login", json={"email": "x@example.com", "password": "nope"}).status_code == 401


def test_unauthenticated_requests_are_rejected(client):
    assert client.get("/api/products").status_code == 401
    assert client.get("/api/products", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_inactive_user_cannot_authenticate(world):
    world.rep.is_active = False
    world.db.commit()
    assert world.api(world.rep).get("/auth/me", expected=None).status_code == 401


def test_catalogue_create_and_duplicate_sku(world):
    api = world.api(world.warehouse_op)   # the Warehouse Manager owns the product master
    data = {"sku": "tyr-100", "brand": "Pirelli", "pattern": "Cinturato P7", "width": 225, "aspect_ratio": 50,
            "rim_diameter": "17", "load_index": "98", "speed_rating": "y", "list_price": "250.00",
            "cost_price": "170.00", "barcode": "8019227000000"}
    created = api.post("/products", data, expected=201).json()
    assert created["sku"] == "TYR-100"
    assert created["size_display"] == "225/50R17"
    assert created["speed_rating"] == "Y"
    api.post("/products", data, expected=409)
    assert world.db.execute(select(Product).where(Product.sku == "TYR-100")).scalar_one().cost_price is not None
    assert world.db.execute(select(AuditEvent).where(AuditEvent.action == "product.create")).scalars().first()


def test_cost_price_hidden_without_permission(world):
    rep_view = world.api(world.rep).get(f"/products/{world.p1.id}").json()
    assert rep_view["cost_price"] is None
    finance_view = world.api(world.finance).get(f"/products/{world.p1.id}").json()
    assert finance_view["cost_price"] == "120.00"


def test_product_write_requires_permission(world):
    data = {"sku": "X-1", "brand": "B", "pattern": "P", "width": 1, "aspect_ratio": 1, "rim_diameter": "1",
            "load_index": "1", "speed_rating": "H"}
    world.api(world.rep).post("/products", data, expected=403)
    world.api(world.manager).post("/products", {**data, "sku": "X-RM"}, expected=201)   # Relationship Manager: may add
    world.api(world.user_a).post("/products", data, expected=403)


def test_product_search_by_size_is_exact(world):
    api = world.api(world.rep)
    rows = api.get("/products", params={"width": 205, "aspect_ratio": 55, "rim_diameter": 16}).json()
    assert {r["sku"] for r in rows} == {"TYR-001", "TYR-003"}  # same size, different SKUs, both listed separately


def test_create_reseller_with_locations_and_agreement(world):
    api = world.api(world.manager)
    data = {
        "account_ref": "rd", "business_name": "Delta Garage", "email": "ops@delta.example.com",
        "contact_name": "Dee Delta", "phone": "09 555 0101", "billing_address": "1 Delta Road, Auckland",
        "sales_rep_user_id": world.rep.id, "payment_terms_days": 14,
        "agreement": {"reference": "AGR-RD", "transfer_consent": "PER_TRANSFER"},
        "locations": [{"code": "rd-north", "name": "Delta North", "address_line1": "1 North St", "city": "Auckland"},
                      {"code": "rd-south", "name": "Delta South", "address_line1": "9 South St", "city": "Auckland"}],
    }
    r = api.post("/resellers", data, expected=201).json()
    assert r["account_ref"] == "RD"
    assert r["sales_rep_name"] == "Riley Rep"
    assert [loc["code"] for loc in r["locations"]] == ["RD-NORTH", "RD-SOUTH"]
    assert all(loc["type"] == "CONSIGNMENT" for loc in r["locations"])
    assert r["agreement"]["transfer_consent"] == "PER_TRANSFER"
    api.post("/resellers", data, expected=409)


def test_reseller_sales_rep_must_be_staff(world):
    api = world.api(world.manager)
    valid = {"account_ref": "RX", "business_name": "X", "contact_name": "X", "email": "x@example.com", "phone": "1",
             "billing_address": "1 X St",
             "locations": [{"code": "RX-1", "name": "X", "address_line1": "1 X St", "city": "Napier"}]}
    api.post("/resellers", {**valid, "sales_rep_user_id": world.user_a.id}, expected=422)      # a dealer user
    api.post("/resellers", {**valid, "sales_rep_user_id": world.manager.id}, expected=422)     # staff, but not a Sales Rep


def test_reseller_status_change_is_audited(world):
    api = world.api(world.manager)
    r = api.post(f"/resellers/{world.reseller_c.id}/status", {"status": "ON_HOLD", "reason": "Overdue account"}).json()
    assert r["status"] == "ON_HOLD"
    ev = world.db.execute(select(AuditEvent).where(AuditEvent.action == "reseller.status")).scalar_one()
    assert "Overdue account" in ev.summary and ev.actor_user_id == world.manager.id


def test_customer_price_effective_dating(world, db):
    from datetime import date
    from decimal import Decimal

    from app.modules.customers.service import effective_price

    api = world.api(world.finance)
    api.post(f"/resellers/{world.reseller_a.id}/prices",
             {"product_id": world.p1.id, "unit_price": "150.00", "valid_from": "2026-01-01"}, expected=201)
    api.post(f"/resellers/{world.reseller_a.id}/prices",
             {"product_id": world.p1.id, "unit_price": "155.00", "valid_from": "2026-07-01"}, expected=201)
    db.expire_all()
    assert effective_price(db, world.reseller_a.id, world.p1, date(2026, 3, 1)) == (Decimal("150.00"), "CUSTOMER_PRICE")
    assert effective_price(db, world.reseller_a.id, world.p1, date(2026, 8, 1)) == (Decimal("155.00"), "CUSTOMER_PRICE")
    assert effective_price(db, world.reseller_a.id, world.p1, date(2025, 8, 1)) == (Decimal("180.00"), "LIST_PRICE")
    assert effective_price(db, world.reseller_b.id, world.p1, date(2026, 8, 1)) == (Decimal("180.00"), "LIST_PRICE")


def test_allocation_target_changes_are_tracked(world):
    api = world.api(world.manager)
    a = api.put("/allocations", {"location_id": world.loc_a.id, "product_id": world.p1.id, "target_qty": 20,
                                 "reason": "Initial agreement"}).json()
    assert a["target_qty"] == 20 and a["auto_replenish"] is True
    api.put("/allocations", {"location_id": world.loc_a.id, "product_id": world.p1.id, "target_qty": 24,
                             "reason": "Seasonal increase"})
    hist = api.get(f"/allocations/{a['id']}/history").json()
    assert [(h["old_target_qty"], h["new_target_qty"]) for h in hist] == [(20, 24), (None, 20)]
    assert world.db.execute(select(AllocationChange)).scalars().all().__len__() == 2


def test_allocation_only_for_consignment_locations(world):
    world.api(world.manager).put(
        "/allocations",
        {"location_id": world.warehouse.id, "product_id": world.p1.id, "target_qty": 5, "reason": "Wrong"},
        expected=422,
    )


def test_user_management_admin_only(world):
    data = {"email": "new@example.com", "full_name": "New Person", "password": "long-enough-pw",
            "role": "SALES_REP"}
    # The Relationship Manager owns the system and administers users; the Warehouse Manager does not.
    world.api(world.warehouse_op).post("/users", data, expected=403)
    world.api(world.rep).post("/users", data, expected=403)
    world.api(world.user_a).post("/users", data, expected=403)
    created = world.api(world.admin).post("/users", data, expected=201).json()
    assert created["role"] == "SALES_REP"
    # Only the four pilot roles exist.
    world.api(world.admin).post("/users", {**data, "email": "x@example.com", "role": "FINANCE"}, expected=422)
    # A reseller user must be linked to a reseller.
    world.api(world.admin).post("/users", {**data, "email": "r@example.com", "role": "RESELLER"}, expected=422)
