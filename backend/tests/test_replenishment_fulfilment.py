"""Release 1.11 — a replenishment request has its own fulfilment flow (finding 22): approve with details, send to a
Relationship Manager, reject with the kind message, mark ready, ship and confirm delivery on the request itself."""

from datetime import date

import pytest

from app.core.messages import KIND_REJECTION
from tests.factories import APPROVAL, HANDOVER, set_stock, set_target

pytestmark = pytest.mark.usefixtures("ledger_balanced")   # every test ends with the ledger reconciled

TODAY = str(date.today())


def _raise(world, user=None, qty=3, note=None):
    set_target(world.db, world.loc_a, world.p1, 6)
    world.db.commit()
    return world.api(user or world.rep).post("/replenishment/requests", {
        "location_id": world.loc_a.id, "product_id": world.p1.id, "quantity": qty, "reason": "Shop is running low",
        "approver_note": note,
    }, expected=201).json()


def _titles(world, user):
    return [n["title"] for n in world.api(user).get("/notifications").json()]


def _url(req, action=""):
    return f"/replenishment/requests/{req['id']}" + (f"/{action}" if action else "")


def test_rep_request_approved_ready_shipped_with_rep_and_delivered(world):
    set_stock(world.db, world.warehouse, world.p1, 10)
    world.db.commit()
    wm, rep, dealer = world.api(world.warehouse_op), world.api(world.rep), world.api(world.user_a)
    req = _raise(world, note="Customer collecting Friday")
    assert req["awaiting_approval"] is True and req["qty_allocated"] == 0
    assert req["notes"] == "Shop is running low\n\nNote for the approver: Customer collecting Friday"
    # The approvers hear about it, with the note.
    for approver in (world.warehouse_op, world.manager):
        [n] = [n for n in world.api(approver).get("/notifications").json()
               if n["title"] == f"{req['number']} is waiting for approval"]
        assert n["body"].endswith("raised by Riley Rep · Customer collecting Friday")
    # Approval needs details; reps cannot approve.
    rep.post(_url(req, "approve"), {"approval": APPROVAL}, expected=403)
    wm.post(_url(req, "approve"), {}, expected=422)
    wm.post(_url(req, "approve"), {"approval": {"method": "PHONE", "comments": "ok then"}}, expected=422)
    out = wm.post(_url(req, "approve"), {"approval": APPROVAL}).json()
    assert out["qty_allocated"] == 3 and out["status"] == "ALLOCATED" and out["awaiting_approval"] is False
    assert (out["approved_by"], out["approval_method"], out["approval_contact"]) == \
        ("Wes Warehouse", "PHONE", "Dealer owner")
    assert f"{req['number']} approved" in _titles(world, world.user_a)
    # Dealers see that it was approved, never the conversation.
    mine = dealer.get(_url(req)).json()
    assert mine["approved_by"] == "Wes Warehouse" and mine["approval_comments"] is None
    assert next(e for e in mine["events"] if e["event_type"] == "APPROVED")["reason"] is None

    # Pick, pack, ship with the rep.
    rep.post(_url(req, "ready"), expected=403)
    ready = wm.post(_url(req, "ready")).json()
    assert ready["ready"] is True and ready["ready_by"] == "Wes Warehouse"
    [row] = [x for x in wm.get("/replenishment/pick-list").json() if x["request_id"] == req["id"]]
    assert row["ready"] is True
    wm.post(_url(req, "ship"), {"shipping_method": "COURIER"}, expected=422)        # which carrier?
    wm.post(_url(req, "ship"), {"shipping_method": "SALES_REP"}, expected=422)      # which rep?
    d = wm.post(_url(req, "ship"), {"shipping_method": "SALES_REP", "carried_by_user_id": world.rep.id},
                expected=201).json()
    assert d["carried_by"] == "Riley Rep" and d["shipping_address"].startswith(world.loc_a.name)
    assert f"Please deliver {d['number']}" in _titles(world, world.rep)
    assert f"{req['number']} has shipped" in _titles(world, world.user_a)
    detail = wm.get(_url(req)).json()
    assert detail["status"] == "IN_TRANSIT" and detail["ready"] is False
    assert [x["number"] for x in detail["deliveries"]] == [d["number"]]

    # Only the carrying rep or the dealer confirms delivery.
    wm.post(f"/replenishment/deliveries/{d['id']}/receive", {}, expected=403)
    rep.post(f"/replenishment/deliveries/{d['id']}/receive", HANDOVER)
    done = wm.get(_url(req)).json()
    assert done["status"] == "FULFILLED" and done["qty_delivered"] == 3
    assert done["deliveries"][0]["received_by_name"] == "Shop owner"
    assert world.bal(world.loc_a, world.p1).on_hand == 3
    assert wm.get("/inventory/reconciliation").json()["balanced"] is True


def test_escalation_to_a_relationship_manager_and_hand_back(world):
    set_stock(world.db, world.warehouse, world.p1, 10)
    world.db.commit()
    wm, rm, other_rm = world.api(world.warehouse_op), world.api(world.manager), world.api(world.admin)
    req = _raise(world, world.user_a)
    wm.post(_url(req, "escalate"), {"to_user_id": world.warehouse_op.id}, expected=422)   # not an RM
    out = wm.post(_url(req, "escalate"), {"to_user_id": world.manager.id, "note": "New dealer"}).json()
    assert out["escalated_to"] == "Morgan Manager" and out["escalation_note"] == "New dealer"
    assert f"Your approval is needed: {req['number']}" in _titles(world, world.manager)
    wm.post(_url(req, "escalate"), {"to_user_id": world.manager.id}, expected=409)        # already waiting
    # While it waits only that RM decides.
    r = wm.post(_url(req, "approve"), {"approval": APPROVAL}, expected=403).json()
    assert r["detail"] == "Waiting for Morgan Manager to approve"
    other_rm.post(_url(req, "approve"), {"approval": APPROVAL}, expected=403)
    wm.post(_url(req, "reject"), {"reason": "Not now"}, expected=403)
    # Dealers never see who it went to.
    mine = world.api(world.user_a).get(_url(req)).json()
    assert mine["escalated_to"] is None and not any(e["event_type"] == "ESCALATED" for e in mine["events"])
    # Hand back: the warehouse decides again.
    rm.post(_url(req, "hand-back"), {"note": "Your call"})
    assert f"{req['number']} handed back to you" in _titles(world, world.warehouse_op)
    wm.post(_url(req, "escalate"), {"to_user_id": world.manager.id})
    approved = rm.post(_url(req, "approve"), {"approval": APPROVAL}).json()
    assert approved["approved_by"] == "Morgan Manager" and approved["escalated_to"] is None
    # The warehouse continues.
    wm.post(_url(req, "ready"))
    wm.post(_url(req, "ship"), {"shipping_method": "COURIER", "carrier": "FastFreight", "tracking_number": "T1"},
            expected=201)


def test_reject_sends_the_kind_message_and_hides_the_reason(world):
    wm = world.api(world.warehouse_op)
    req = _raise(world, world.user_a)
    out = wm.post(_url(req, "reject"), {"reason": "Dealer is over their credit limit"}).json()
    assert out["status"] == "CANCELLED" and out["qty_cancelled"] == 3
    notes = world.api(world.user_a).get("/notifications").json()
    kind = next(n for n in notes if n["title"] == f"Update on your request {req['number']}")
    assert kind["body"] == KIND_REJECTION
    assert not any("credit limit" in (n["body"] or "") for n in notes)
    mine = world.api(world.user_a).get(_url(req)).json()
    assert next(e for e in mine["events"] if e["event_type"] == "REJECTED")["reason"] == KIND_REJECTION
    assert "credit limit" not in str(mine)
    # Staff (including the dealer's rep) keep the reason.
    staff = wm.get(_url(req)).json()
    assert next(e for e in staff["events"] if e["event_type"] == "REJECTED")["reason"] == \
        "Dealer is over their credit limit"
    assert any("credit limit" in (n["body"] or "") for n in world.api(world.rep).get("/notifications").json())
    wm.post(_url(req, "reject"), {"reason": "Again"}, expected=409)


def test_sale_triggered_request_shows_as_approved_automatically(world):
    set_stock(world.db, world.warehouse, world.p1, 10)
    world.db.commit()
    rm, dealer = world.api(world.manager), world.api(world.user_a)
    rm.post(f"/resellers/{world.reseller_a.id}/initial-stock",
            {"location_id": world.loc_a.id, "lines": [{"product_id": world.p1.id, "quantity": 6}]}, expected=201)
    sale = dealer.post("/sales", {"location_id": world.loc_a.id, "sale_date": TODAY,
                                  "lines": [{"product_id": world.p1.id, "quantity": 2}]}, expected=201).json()
    [req] = [r for r in rm.get("/replenishment/requests").json() if r["origin_number"] == sale["number"]]
    assert req["auto_approved"] is True and req["awaiting_approval"] is False and req["approved_by"] is None
    # It goes straight to the warehouse.
    world.api(world.warehouse_op).post(_url(req, "ready"))
    assert world.api(world.warehouse_op).get(_url(req)).json()["ready"] is True


def test_stock_request_lines_are_managed_on_their_stock_request(world):
    set_stock(world.db, world.warehouse, world.p1, 10)
    world.db.commit()
    wm = world.api(world.warehouse_op)
    sr = world.api(world.user_a).post("/stock-requests", {"location_id": world.loc_a.id, "submit": True,
                                                          "lines": [{"product_id": world.p1.id, "quantity": 2}]}).json()
    wm.post(f"/stock-requests/{sr['id']}/decision",
            {"lines": [{"line_id": sr["lines"][0]["id"], "approve_qty": 2}], "approval": APPROVAL})
    [req] = [r for r in wm.get("/replenishment/requests").json() if r["origin_number"] == sr["number"]]
    for action, body in (("approve", {"approval": APPROVAL}), ("escalate", {"to_user_id": world.manager.id}),
                         ("hand-back", {}), ("reject", {"reason": "Not this time"}), ("ready", None),
                         ("ship", {"shipping_method": "COURIER", "carrier": "X"})):
        r = wm.post(_url(req, action), body, expected=409).json()
        assert r["detail"] == f"Managed on {sr['number']}"


def test_dealers_cannot_reach_other_dealers_requests_or_act_on_their_own(world):
    req = _raise(world, world.user_a)
    world.api(world.user_b).get(_url(req), expected=404)
    for action in ("approve", "escalate", "reject", "ready", "ship"):
        world.api(world.user_a).post(_url(req, action), {}, expected=403)
