"""Release 1.11 — a dealer orders stock (findings 16–21): approval details, escalation to a Relationship Manager,
dealer holdings on approval, the kind rejection message and 'please call me'."""

import pytest

from app.core.messages import KIND_REJECTION
from app.modules.customers.models import Location, LocationType
from tests.factories import APPROVAL, HANDOVER, set_stock

pytestmark = pytest.mark.usefixtures("ledger_balanced")   # every test ends with the ledger reconciled


def _request(world, lines=None):
    lines = lines or [{"product_id": world.p1.id, "quantity": 4}]
    return world.api(world.user_a).post("/stock-requests", {"location_id": world.loc_a.id, "submit": True,
                                                            "lines": lines}).json()


def _decide(api, sr, decisions, approval=APPROVAL, expected=200, notes=None):
    body = {"lines": [{"line_id": ln["id"], **d} for ln, d in zip(sr["lines"], decisions, strict=True)], "notes": notes}
    if approval is not None:
        body["approval"] = approval
    return api.post(f"/stock-requests/{sr['id']}/decision", body, expected=expected).json()


def _titles(world, user):
    return [n["title"] for n in world.api(user).get("/notifications").json()]


def test_approval_details_are_required_and_stored(world):
    set_stock(world.db, world.warehouse, world.p1, 10)
    world.db.commit()
    wm = world.api(world.warehouse_op)
    sr = _request(world)
    _decide(wm, sr, [{"approve_qty": 4}], approval=None, expected=422)
    _decide(wm, sr, [{"approve_qty": 4}], approval={"method": "PHONE", "comments": "ok then"}, expected=422)   # who?
    _decide(wm, sr, [{"approve_qty": 4}], approval={"method": "STANDARD", "comments": "x"}, expected=422)     # too short
    done = _decide(wm, sr, [{"approve_qty": 4}], approval={"method": "STANDARD", "comments": "Standard top-up"})
    assert (done["approval_method"], done["approval_contact"], done["approval_comments"]) == ("STANDARD", None, "Standard top-up")
    assert done["reviewed_by"] == "Wes Warehouse"
    event = next(e for e in done["events"] if e["action"] == "APPROVED")
    assert event["details"]["approval"] == {"method": "STANDARD", "contact": None, "comments": "Standard top-up"}
    # Staff only.
    mine = world.api(world.user_a).get(f"/stock-requests/{sr['id']}").json()
    assert mine["approval_method"] is None and mine["approval_comments"] is None
    # A full rejection needs no approval details.
    sr2 = _request(world)
    world.api(world.warehouse_op).post(f"/stock-requests/{sr2['id']}/reject", {"reason": "Not stocked for this dealer"})


def test_escalation_to_a_relationship_manager(world):
    set_stock(world.db, world.warehouse, world.p1, 10)
    world.db.commit()
    wm, rm, admin_rm = world.api(world.warehouse_op), world.api(world.manager), world.api(world.admin)
    sr = _request(world)
    wm.post(f"/stock-requests/{sr['id']}/escalate", {"to_user_id": world.warehouse_op.id}, expected=422)   # not an RM
    world.api(world.user_a).post(f"/stock-requests/{sr['id']}/escalate", {"to_user_id": world.manager.id}, expected=403)
    out = wm.post(f"/stock-requests/{sr['id']}/escalate", {"to_user_id": world.manager.id, "note": "Big order"}).json()
    assert out["status"] == "UNDER_REVIEW" and out["escalated_to"] == "Morgan Manager" and out["escalation_note"] == "Big order"
    assert f"Your approval is needed: {sr['number']}" in _titles(world, world.manager)
    # Only that RM (or an Administrator) decides while it waits.
    r = wm.post(f"/stock-requests/{sr['id']}/decision", {"lines": [{"line_id": sr["lines"][0]["id"], "approve_qty": 4}],
                                                         "approval": APPROVAL}, expected=403).json()
    assert r["detail"] == "Waiting for Morgan Manager to approve"
    _decide(admin_rm, sr, [{"approve_qty": 4}], expected=403)          # another RM
    wm.post(f"/stock-requests/{sr['id']}/reject", {"reason": "Not this time"}, expected=403)
    assert world.api(world.user_a).get(f"/stock-requests/{sr['id']}").json()["escalated_to"] is None   # dealer
    done = _decide(rm, sr, [{"approve_qty": 4}])
    assert done["status"] == "APPROVED"
    # The warehouse continues as normal.
    assert wm.post(f"/stock-requests/{sr['id']}/ready").json()["status"] == "READY_FOR_SHIPMENT"
    shipped = wm.post(f"/stock-requests/{sr['id']}/ship",
                      {"shipping_method": "SALES_REP", "carried_by_user_id": world.rep.id}).json()
    assert shipped["status"] == "SHIPPED"
    world.api(world.rep).post(f"/stock-requests/{sr['id']}/shipments/{shipped['shipments'][0]['id']}/confirm", HANDOVER)
    assert world.api(world.warehouse_op).get("/inventory/reconciliation").json()["balanced"] is True


def test_hand_back_returns_the_decision_to_the_warehouse(world):
    set_stock(world.db, world.warehouse, world.p1, 10)
    world.db.commit()
    wm, rm = world.api(world.warehouse_op), world.api(world.manager)
    sr = _request(world)
    wm.post(f"/stock-requests/{sr['id']}/escalate", {"to_user_id": world.manager.id})
    wm.post(f"/stock-requests/{sr['id']}/hand-back", {}, expected=403)       # only the RM hands back
    back = rm.post(f"/stock-requests/{sr['id']}/hand-back", {"note": "Your call"}).json()
    assert back["escalated_to_user_id"] is None
    assert f"{sr['number']} handed back to you" in _titles(world, world.warehouse_op)
    assert _decide(wm, sr, [{"approve_qty": 4}])["status"] == "APPROVED"


def test_dealer_sees_the_kind_message_never_the_reason(world):
    set_stock(world.db, world.warehouse, world.p1, 2)
    world.db.commit()
    wm = world.api(world.warehouse_op)
    sr = _request(world)
    # Partial: 2 approved, 2 rejected with an internal reason.
    _decide(wm, sr, [{"approve_qty": 2, "remainder": "REJECT", "notes": "Dealer is over their credit limit"}],
            notes="Internal: credit hold")
    alpha = world.api(world.user_a)
    mine = alpha.get(f"/stock-requests/{sr['id']}").json()
    text = str(mine)
    assert "credit" not in text.lower()
    assert mine["review_notes"] == KIND_REJECTION and mine["lines"][0]["decision_notes"] == KIND_REJECTION
    assert any(KIND_REJECTION in e["summary"] for e in mine["events"])
    assert all(e["details"] is None for e in mine["events"])
    assert "credit" not in str(alpha.get("/stock-requests").json()).lower()
    notes = alpha.get("/notifications").json()
    kind = [n for n in notes if n["title"] == f"Update on your order {sr['number']}"]
    assert kind and kind[0]["body"].startswith(KIND_REJECTION)
    assert not any("credit" in f"{n['title']} {n['body']}".lower() for n in notes)
    # Staff still see the reason.
    assert "credit" in str(wm.get(f"/stock-requests/{sr['id']}").json()).lower()
    # A full rejection too.
    sr2 = _request(world)
    wm.post(f"/stock-requests/{sr2['id']}/reject", {"reason": "Brand discontinued for this dealer"})
    mine2 = alpha.get(f"/stock-requests/{sr2['id']}").json()
    assert mine2["status"] == "REJECTED" and mine2["review_notes"] == KIND_REJECTION and "discontinued" not in str(mine2)


def test_please_call_me_notifies_the_rm_and_the_rep(world):
    sr = _request(world)
    world.api(world.user_a).post(f"/stock-requests/{sr['id']}/callback", {"preferred_time": "Tomorrow 9am", "phone": "021 555"})
    title = f"Alpha Tyres would like a call about {sr['number']}"
    assert title in _titles(world, world.manager) and title in _titles(world, world.rep)
    world.api(world.rep).post(f"/stock-requests/{sr['id']}/callback", {"preferred_time": "Today", "phone": "021 5"})
    world.api(world.warehouse_op).post(f"/stock-requests/{sr['id']}/callback", {"preferred_time": "x y", "phone": "123"},
                                       expected=403)
    world.api(world.user_b).post(f"/stock-requests/{sr['id']}/callback", {"preferred_time": "x y", "phone": "123"},
                                 expected=404)


def test_dealer_on_hand_shows_what_the_dealer_already_holds(world):
    db = world.db
    second = Location(code="RA-2", name="Alpha 2", type=LocationType.CONSIGNMENT, reseller_id=world.reseller_a.id)
    db.add(second)
    db.flush()
    set_stock(db, world.loc_a, world.p1, 7)
    set_stock(db, second, world.p1, 2)
    db.commit()
    sr = _request(world, [{"product_id": world.p1.id, "quantity": 3}, {"product_id": world.p2.id, "quantity": 1}])
    lines = world.api(world.warehouse_op).get(f"/stock-requests/{sr['id']}").json()["lines"]
    assert [(ln["dealer_on_hand"], ln["dealer_on_hand_all"]) for ln in lines] == [(7, 9), (0, 0)]
    mine = world.api(world.user_a).get(f"/stock-requests/{sr['id']}").json()["lines"]
    assert all(ln["dealer_on_hand"] is None and ln["dealer_on_hand_all"] is None for ln in mine)
