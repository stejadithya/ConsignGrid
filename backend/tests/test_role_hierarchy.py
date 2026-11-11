"""Release 1.11 role hierarchy: Warehouse Manager ⊆ Relationship Manager ⊆ Administrator, Finance Manager ⊆ RM
(findings 1 and 2, decisions D1 and P-028/P-029)."""

import pytest

from app.core.permissions import ROLE_PERMISSIONS, P, Role
from tests.factories import APPROVAL, make_user, set_stock

pytestmark = pytest.mark.usefixtures("ledger_balanced")   # every test ends with the ledger reconciled

ADMIN, RM, WM, FM, SR, DLR = (ROLE_PERMISSIONS[r] for r in (
    Role.ADMINISTRATOR, Role.RELATIONSHIP_MANAGER, Role.WAREHOUSE_MANAGER, Role.FINANCE_MANAGER, Role.SALES_REP,
    Role.RESELLER))


def test_roles_nest():
    assert WM <= RM <= ADMIN
    assert FM <= RM
    assert P.INVOICE_REFERENCE_READ in RM and P.INVOICE_REFERENCE_READ in FM
    assert P.INVOICE_REFERENCE_READ not in WM | SR | DLR
    # The Finance Manager takes no stock actions.
    assert not ({P.INVENTORY_RECEIVE, P.INVENTORY_ADJUST, P.INVENTORY_BLOCK, P.PURCHASING_MANAGE, P.DISPATCH,
                 P.SALES_RECORD, P.STOCK_REQUEST_APPROVE, P.TRANSFER_REQUEST, P.CATALOGUE_WRITE} & FM)


def test_dealer_permissions_are_unchanged():
    assert {P.CATALOGUE_READ, P.INVENTORY_READ, P.SALES_RECORD, P.REPLENISHMENT_READ, P.REPLENISHMENT_REQUEST,
                   P.TRANSFER_READ, P.INVOICE_READ, P.REPORT_READ, P.FEEDBACK_SUBMIT, P.STOCK_REQUEST_READ,
                   P.STOCK_REQUEST_CREATE, P.DELIVERY_CONFIRM, P.STOCKTAKE_CONFIRM} == DLR


def test_relationship_manager_does_warehouse_work_through_the_api(world):
    db = world.db
    set_stock(db, world.warehouse, world.p1, 10)
    db.commit()
    rm = world.api(world.manager)
    # Purchase order and goods receipt.
    po = rm.post("/purchasing/purchase-orders", {"supplier_name": "S", "warehouse_location_id": world.warehouse.id,
                                                 "lines": [{"product_id": world.p2.id, "qty_ordered": 4}]},
                 expected=201).json()
    rm.post("/purchasing/receipts", {"warehouse_location_id": world.warehouse.id, "purchase_order_id": po["id"],
                                     "lines": [{"product_id": world.p2.id, "qty_received": 4,
                                                "purchase_order_line_id": po["lines"][0]["id"]}]}, expected=201)
    assert world.bal(world.warehouse, world.p2).on_hand == 4
    # Stock adjustment.
    rm.post("/inventory/adjustments", {"location_id": world.warehouse.id, "product_id": world.p1.id,
                                       "quantity_delta": -1, "reason": "Damaged in handling"}, expected=201)
    assert world.bal(world.warehouse, world.p1).on_hand == 9
    # Replenishment dispatch.
    req = rm.post("/replenishment/requests", {"location_id": world.loc_a.id, "product_id": world.p1.id,
                                              "quantity": 2, "reason": "Top up"}, expected=201).json()
    if req["qty_allocated"] < 2:
        req = rm.post(f"/replenishment/requests/{req['id']}/allocate", {}).json()
    d = rm.post("/replenishment/deliveries", {"to_location_id": world.loc_a.id, "lines": [{"request_id": req["id"]}]},
                expected=201).json()
    assert d["status"] == "IN_TRANSIT"
    # Stock request: approve, mark ready and ship.
    sr = world.api(world.user_a).post("/stock-requests", {"location_id": world.loc_a.id, "submit": True,
                                                         "lines": [{"product_id": world.p1.id, "quantity": 2}]}).json()
    sr = rm.post(f"/stock-requests/{sr['id']}/decision",
                 {"lines": [{"line_id": sr["lines"][0]["id"], "approve_qty": 2}], "approval": APPROVAL}).json()
    sr = rm.post(f"/stock-requests/{sr['id']}/ready").json()
    assert sr["status"] == "READY_FOR_SHIPMENT"
    assert rm.post(f"/stock-requests/{sr['id']}/ship", {"carrier": "StarTrack"}).json()["status"] == "SHIPPED"
    # Product master edits.
    assert rm.patch(f"/products/{world.p1.id}", {"pattern": "Primacy 5"}).json()["pattern"] == "Primacy 5"
    assert world.api(world.warehouse_op).get("/inventory/reconciliation").json()["balanced"] is True


def test_ready_to_pick_still_goes_to_the_warehouse_only(world):
    set_stock(world.db, world.warehouse, world.p1, 5)
    world.db.commit()
    rm = world.api(world.manager)
    sr = world.api(world.user_a).post("/stock-requests", {"location_id": world.loc_a.id, "submit": True,
                                                         "lines": [{"product_id": world.p1.id, "quantity": 1}]}).json()
    rm.post(f"/stock-requests/{sr['id']}/decision", {"lines": [{"line_id": sr["lines"][0]["id"], "approve_qty": 1}],
                                                    "approval": APPROVAL})
    ready = lambda u: [n for n in world.api(u).get("/notifications").json() if "ready to pick" in n["title"]]  # noqa: E731
    assert ready(world.warehouse_op)
    assert not ready(world.manager)


def test_finance_manager_reads_invoices_but_cannot_touch_stock(world):
    fm = world.api(make_user(world.db, Role.FINANCE_MANAGER, "fm@example.com", name="Fran Finance"))
    world.db.commit()
    fm.get("/invoices", expected=200)
    fm.get("/invoices/uninvoiced", expected=200)
    fm.get("/sales", expected=200)
    fm.get("/resellers", expected=200)
    fm.get("/reports/dashboard", expected=200)
    fm.post("/inventory/adjustments", {"location_id": world.warehouse.id, "product_id": world.p1.id,
                                       "quantity_delta": 1, "reason": "x"}, expected=403)
    fm.post("/purchasing/purchase-orders", {"supplier_name": "S", "warehouse_location_id": world.warehouse.id,
                                            "lines": [{"product_id": world.p1.id, "qty_ordered": 1}]}, expected=403)
    fm.post("/sales", {"location_id": world.loc_a.id, "lines": [{"product_id": world.p1.id, "quantity": 1}]},
            expected=403)
    fm.post("/stock-requests", {"location_id": world.loc_a.id, "lines": [{"product_id": world.p1.id, "quantity": 1}]},
            expected=403)
    fm.get("/users", expected=403)
