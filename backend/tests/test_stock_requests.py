"""Consignment stock requests: multi-SKU request → Central Team approval → reservation → shipment → delivery."""

from datetime import date, timedelta

from app.core.config import get_settings
from app.core.permissions import Role
from app.modules.customers.models import ResellerStatus
from tests.factories import APPROVAL, HANDOVER, make_user, set_stock

TODAY = date.today()


def _request(api, world, lines, *, submit=True, expected=201, **extra):
    body = {"location_id": world.loc_a.id, "lines": lines, "submit": submit, **extra}
    return api.post("/stock-requests", body, expected=expected).json()


def _lines(world, q1=6, q2=4):
    return [{"product_id": world.p1.id, "quantity": q1, "notes": "Winter promo"},
            {"product_id": world.p2.id, "quantity": q2}]


def _decide(api, sr, decisions, expected=200, notes=None):
    body = {"lines": [{"line_id": ln["id"], **d} for ln, d in zip(sr["lines"], decisions, strict=True)],
            "notes": notes, "approval": APPROVAL}   # approval details are required since 1.11 (finding 17)
    return api.post(f"/stock-requests/{sr['id']}/decision", body, expected=expected).json()


def test_full_lifecycle_partial_approval_backorder_ship_deliver(world):
    db = world.db
    set_stock(db, world.warehouse, world.p1, 10)
    set_stock(db, world.warehouse, world.p2, 2)
    db.commit()
    rep, rm, wm, alpha = (world.api(u) for u in (world.rep, world.manager, world.warehouse_op, world.user_a))

    # Sales rep raises a request on behalf of reseller A; created-by and role are recorded.
    sr = _request(rep, world, _lines(world), required_date=str(TODAY + timedelta(days=3)), notes="For the weekend")
    assert sr["status"] == "SUBMITTED" and sr["number"].startswith("SRQ-")
    assert sr["created_by"] == "Riley Rep" and sr["created_by_role"] == "SALES_REP"
    assert sr["qty_requested"] == 10 and sr["line_count"] == 2
    # Nothing is reserved before approval.
    assert world.bal(world.warehouse, world.p1).reserved == 0

    # The Central Team is notified; the reseller sees its own request.
    assert rm.get("/notifications/unread-count").json()["unread"] >= 1
    assert any(r["id"] == sr["id"] for r in alpha.get("/stock-requests", params={"view": "mine"}).json())
    assert [r["id"] for r in rm.get("/stock-requests", params={"view": "pending"}).json()] == [sr["id"]]

    # Shipping before approval is refused.
    wm.post(f"/stock-requests/{sr['id']}/ship", {"carrier": "StarTrack"}, expected=409)

    sr = rm.post(f"/stock-requests/{sr['id']}/review").json()
    assert sr["status"] == "UNDER_REVIEW"
    # Approving more than is available is refused (approved ≤ available).
    _decide(rm, sr, [{"approve_qty": 6}, {"approve_qty": 4}], expected=422)

    # p1 fully approved; p2: 2 approved, remaining 2 backordered.
    sr = _decide(rm, sr, [{"approve_qty": 6}, {"approve_qty": 2, "remainder": "BACKORDER"}], notes="Short on p2")
    assert sr["status"] == "PARTIALLY_APPROVED" and sr["reviewed_by"] == "Morgan Manager"
    l1, l2 = sr["lines"]
    assert (l1["qty_approved"], l1["qty_reserved"], l1["qty_backordered"]) == (6, 6, 0)
    assert (l2["qty_approved"], l2["qty_reserved"], l2["qty_backordered"], l2["qty_rejected"]) == (2, 2, 2, 0)
    assert l2["qty_backorder_open"] == 2
    # Reservation prevents double allocation.
    assert world.bal(world.warehouse, world.p1).reserved == 6
    assert world.bal(world.warehouse, world.p2).available == 0
    approval = next(e for e in sr["events"] if e["action"] == "PARTIALLY_APPROVED")
    assert approval["actor_role"] == "RELATIONSHIP_MANAGER"
    assert {d["sku"]: (d["requested"], d["approved"], d["backordered"]) for d in approval["details"]["lines"]} == {
        "TYR-001": (6, 6, 0), "TYR-002": (4, 2, 2)}
    # Reseller and sales rep are notified of the decision.
    assert any("partially approved" in n["title"] for n in alpha.get("/notifications").json())

    # A second request cannot take the reserved stock.
    sr_b = _request(rm, world, [{"product_id": world.p2.id, "quantity": 1}], location_id=world.loc_b.id)
    _decide(rm, sr_b, [{"approve_qty": 1}], expected=422)

    # Warehouse marks ready and ships; shipped ≤ reserved.
    sr = wm.post(f"/stock-requests/{sr['id']}/ready").json()
    assert sr["status"] == "READY_FOR_SHIPMENT"
    wm.post(f"/stock-requests/{sr['id']}/ship", {"carrier": "StarTrack", "lines": [
        {"line_id": l1["id"], "quantity": 7}]}, expected=422)
    sr = wm.post(f"/stock-requests/{sr['id']}/ship", {
        "carrier": "StarTrack", "tracking_number": "ST123", "notes": "2 pallets"}).json()
    assert sr["status"] == "SHIPPED" and sr["qty_shipped"] == 8
    shipment = sr["shipments"][0]
    assert shipment["tracking_number"] == "ST123" and shipment["carrier_reference"] == "StarTrack"
    assert shipment["stock_request_number"] == sr["number"] and shipment["shipping_address"]
    assert world.bal(world.warehouse, world.p1).on_hand == 4

    # Inventory overview: Total = warehouse + shipped; Available = Total − Reserved − Shipped.
    inv = {r["sku"]: r for r in rm.get("/stock-requests/inventory/overview").json()}
    assert inv["TYR-001"]["shipped"] == 6 and inv["TYR-001"]["total"] == 10
    assert inv["TYR-001"]["available"] == inv["TYR-001"]["total"] - inv["TYR-001"]["reserved"] - 6

    # The reseller confirms delivery: one unit short on p2.
    p2_line = next(ln for ln in shipment["lines"] if ln["product_id"] == world.p2.id)
    alpha.post(f"/stock-requests/{sr['id']}/shipments/{shipment['id']}/confirm", {
        "lines": [{"line_id": p2_line["id"], "qty_received": 3}]}, expected=422)  # delivered ≤ shipped
    sr = alpha.post(f"/stock-requests/{sr['id']}/shipments/{shipment['id']}/confirm", {
        "lines": [{"line_id": p2_line["id"], "qty_received": 2}], "reference": "POD-77",
        "delivered_on": str(TODAY)}).json()
    assert sr["status"] == "DELIVERED" and sr["qty_delivered"] == 8
    assert sr["shipments"][0]["delivery_reference"] == "POD-77"
    assert world.bal(world.loc_a, world.p1).on_hand == 6
    assert sr["closed_at"] is None   # the p2 backorder is still open

    # Stock arrives: the Central Team reserves the backorder, which becomes approved, then it ships again.
    set_stock(db, world.warehouse, world.p2, 5)
    db.commit()
    sr = rm.post(f"/stock-requests/{sr['id']}/lines/{l2['id']}/reserve", {}).json()
    l2 = sr["lines"][1]
    assert (l2["qty_approved"], l2["qty_backordered"], l2["qty_reserved"]) == (4, 0, 2)
    sr = wm.post(f"/stock-requests/{sr['id']}/ship", {"carrier": "Toll"}).json()
    second = sr["shipments"][1]
    sr = rep.post(f"/stock-requests/{sr['id']}/shipments/{second['id']}/confirm", HANDOVER).json()
    assert sr["status"] == "DELIVERED" and sr["closed_at"] is not None
    assert world.bal(world.loc_a, world.p2).on_hand == 4

    actions = [e["action"] for e in sr["events"]]
    for a in ("CREATED", "SUBMITTED", "REVIEW_STARTED", "PARTIALLY_APPROVED", "READY_FOR_SHIPMENT", "SHIPPED",
              "DELIVERED", "RESERVED"):
        assert a in actions
    audit = world.api(world.admin).get("/audit-events", params={"entity_type": "stock_request"}).json()
    assert any(a["action"] == "stock_request.partially_approved" for a in audit)


def test_draft_edit_validation_and_cancel(world):
    db = world.db
    alpha = world.api(world.user_a)
    settings = get_settings()

    # Validations: quantity > 0, configured limit, active SKU, no duplicates, date not in the past.
    _request(alpha, world, [{"product_id": world.p1.id, "quantity": 0}], expected=422)
    _request(alpha, world, [{"product_id": world.p1.id, "quantity": settings.stock_request_max_line_qty + 1}],
             expected=422)
    _request(alpha, world, [{"product_id": world.p1.id, "quantity": 1}, {"product_id": world.p1.id, "quantity": 2}],
             expected=422)
    _request(alpha, world, [{"product_id": world.p1.id, "quantity": 1}], expected=422,
             required_date=str(TODAY - timedelta(days=1)))
    _request(alpha, world, [{"product_id": world.p1.id, "quantity": 1}], expected=422, priority="URGENT")
    world.p3.is_active = False
    db.commit()
    _request(alpha, world, [{"product_id": world.p3.id, "quantity": 1}], expected=422)
    # Resellers cannot request for another reseller's location.
    _request(alpha, world, [{"product_id": world.p1.id, "quantity": 1}], expected=404, location_id=world.loc_b.id)

    draft = _request(alpha, world, [{"product_id": world.p1.id, "quantity": 2}], submit=False)
    assert draft["status"] == "DRAFT"
    # Drafts are private to the requester's side.
    world.api(world.manager).get(f"/stock-requests/{draft['id']}", expected=404)
    edited = alpha.put(f"/stock-requests/{draft['id']}", {"lines": [
        {"product_id": world.p1.id, "quantity": 3}, {"product_id": world.p2.id, "quantity": 1}]}).json()
    assert edited["qty_requested"] == 4 and edited["line_count"] == 2
    submitted = alpha.post(f"/stock-requests/{draft['id']}/submit").json()
    assert submitted["status"] == "SUBMITTED"
    alpha.put(f"/stock-requests/{draft['id']}", {"lines": [{"product_id": world.p1.id, "quantity": 1}]},
              expected=409)
    cancelled = alpha.post(f"/stock-requests/{draft['id']}/cancel", {"reason": "Ordered by mistake"}).json()
    assert cancelled["status"] == "CANCELLED"


def test_rbac_and_isolation(world):
    db = world.db
    set_stock(db, world.warehouse, world.p1, 5)
    db.commit()
    alpha, bravo, rep, rm, wm = (world.api(u) for u in (world.user_a, world.user_b, world.rep, world.manager,
                                                          world.warehouse_op))
    sr = _request(alpha, world, [{"product_id": world.p1.id, "quantity": 2}])
    # Resellers are isolated from each other.
    bravo.get(f"/stock-requests/{sr['id']}", expected=404)
    assert bravo.get("/stock-requests").json() == []
    # Reseller and sales rep cannot approve, reject, reserve or ship.
    for api in (alpha, rep):
        _decide(api, sr, [{"approve_qty": 2}], expected=403)
        api.post(f"/stock-requests/{sr['id']}/reject", {"reason": "nope"}, expected=403)
        api.post(f"/stock-requests/{sr['id']}/ship", {"carrier": "x"}, expected=403)
    # Sales reps keep seeing all resellers' requests.
    assert any(r["id"] == sr["id"] for r in rep.get("/stock-requests").json())
    # The warehouse manager is part of the Central Team and can approve; the RM can also ship (P-028).
    sr = _decide(wm, sr, [{"approve_qty": 2}])
    assert sr["status"] == "APPROVED"
    assert rm.post(f"/stock-requests/{sr['id']}/ship", {"carrier": "x"}).json()["status"] == "SHIPPED"
    # Warehouse stock overview is staff-only.
    alpha.get("/stock-requests/inventory/overview", expected=403)
    # Notifications are private.
    note = alpha.get("/notifications").json()[0]
    bravo.post(f"/notifications/{note['id']}/read", expected=404)
    alpha.post(f"/notifications/{note['id']}/read")
    alpha.post("/notifications/read-all")
    assert alpha.get("/notifications/unread-count").json()["unread"] == 0


def test_reject_release_and_inactive_reseller(world):
    db = world.db
    set_stock(db, world.warehouse, world.p1, 5)
    db.commit()
    rm, alpha = world.api(world.manager), world.api(world.user_a)

    sr = _request(alpha, world, [{"product_id": world.p1.id, "quantity": 3}])
    rejected = rm.post(f"/stock-requests/{sr['id']}/reject", {"reason": "Over target"}).json()
    assert rejected["status"] == "REJECTED" and rejected["lines"][0]["qty_rejected"] == 3
    assert world.bal(world.warehouse, world.p1).reserved == 0

    # Partial approval with the remainder rejected.
    sr = _request(alpha, world, [{"product_id": world.p1.id, "quantity": 4}])
    sr = _decide(rm, sr, [{"approve_qty": 3, "remainder": "REJECT"}])
    assert sr["status"] == "PARTIALLY_APPROVED"
    assert (sr["lines"][0]["qty_approved"], sr["lines"][0]["qty_rejected"]) == (3, 1)
    # Release returns the reserved stock to availability.
    line = sr["lines"][0]
    sr = rm.post(f"/stock-requests/{sr['id']}/lines/{line['id']}/release", {"reason": "Customer postponed"}).json()
    assert world.bal(world.warehouse, world.p1).reserved == 0
    assert sr["lines"][0]["qty_released"] == 3 and sr["lines"][0]["qty_reserved"] == 0
    world.api(world.warehouse_op).post(f"/stock-requests/{sr['id']}/ship", {"carrier": "x"}, expected=422)

    # Inactive reseller: requests and approvals are refused.
    pending = _request(alpha, world, [{"product_id": world.p1.id, "quantity": 1}])
    world.reseller_a.status = ResellerStatus.ON_HOLD
    db.commit()
    _decide(rm, pending, [{"approve_qty": 1}], expected=422)
    _request(alpha, world, [{"product_id": world.p1.id, "quantity": 1}], expected=422)


def test_manual_replenishment_from_reseller_or_rep_waits_for_approval(world):
    """Approval gate: reseller / sales rep replenishment requests reserve nothing until staff allocate."""
    db = world.db
    set_stock(db, world.warehouse, world.p1, 10)
    from tests.factories import set_target
    set_target(db, world.loc_a, world.p1, 6)
    db.commit()
    body = {"location_id": world.loc_a.id, "product_id": world.p1.id, "quantity": 2, "reason": "Customer asked"}
    req = world.api(world.user_a).post("/replenishment/requests", body, expected=201).json()
    assert req["qty_allocated"] == 0 and req["qty_awaiting_supply"] == 2
    staff = world.api(world.manager).post("/replenishment/requests", {**body, "quantity": 1}, expected=201).json()
    assert staff["qty_allocated"] == 1   # staff requests keep auto-allocation
    world.api(world.warehouse_op).post(f"/replenishment/requests/{req['id']}/allocate", {"quantity": 2})


def test_administrator_has_full_access(world):
    db = world.db
    set_stock(db, world.warehouse, world.p1, 3)
    admin = make_user(db, Role.ADMINISTRATOR, "root@example.com", name="Root Admin")
    db.commit()
    api = world.api(admin)
    sr = _request(api, world, [{"product_id": world.p1.id, "quantity": 2}])
    sr = _decide(api, sr, [{"approve_qty": 2}])
    sr = api.post(f"/stock-requests/{sr['id']}/ship", {"carrier": "Courier"}).json()
    assert sr["status"] == "SHIPPED"
    allocs = api.get("/stock-requests/inventory/allocations").json()
    assert allocs == []
    assert api.get("/stock-requests/summary").json()["in_transit"] == 1
