"""Release 1.11 — staff handover when someone leaves (finding 32, D9): dealers, carried deliveries and transfers, and
waiting approvals move to a colleague with the same role; nobody is deactivated while things are still theirs."""

import pytest

from app.core.permissions import Role
from app.modules.customers.models import Reseller
from tests.factories import APPROVAL, HANDOVER, make_user, set_stock

pytestmark = pytest.mark.usefixtures("ledger_balanced")   # every test ends with the ledger reconciled


def _rep_delivery(world):
    """A delivery to Alpha carried by Riley Rep, still in transit."""
    set_stock(world.db, world.warehouse, world.p1, 5)
    world.db.commit()
    req = world.api(world.manager).post("/replenishment/requests", {
        "location_id": world.loc_a.id, "product_id": world.p1.id, "quantity": 2, "reason": "Top-up"}).json()
    return world.api(world.warehouse_op).post("/replenishment/deliveries", {
        "to_location_id": world.loc_a.id, "lines": [{"request_id": req["id"], "quantity": 2}],
        "shipping_method": "SALES_REP", "carried_by_user_id": world.rep.id}, expected=201).json()


def _rep_transfer(world):
    """A transfer Alpha → Bravo that Riley Rep is asked to carry (approved, not yet collected)."""
    set_stock(world.db, world.loc_a, world.p3, 4)
    world.db.commit()
    mgr = world.api(world.manager)
    t = mgr.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p3.id, "quantity": 1,
                                "reason": "Customer waiting"}, expected=201).json()
    return mgr.post(f"/transfers/{t['id']}/approve", {
        "source_location_id": world.loc_a.id, "source_consent_reference": "Phoned",
        "shipping": {"shipping_method": "SALES_REP", "carried_by_user_id": world.rep.id}}).json()


def test_a_full_takeover_moves_everything_and_deactivates_the_leaver(world):
    new_rep = make_user(world.db, Role.SALES_REP, "new.rep@example.com", name="Nova Rep")
    world.db.commit()
    d, t = _rep_delivery(world), _rep_transfer(world)
    rm = world.api(world.manager)
    out = rm.post(f"/users/{world.rep.id}/handover", {"to_user_id": new_rep.id, "deactivate": True,
                                                       "reason": "Resigned"}).json()
    assert (out["dealers"], out["deliveries"], out["transfers"], out["deactivated"]) == (2, 1, 1, True)
    world.db.expire_all()
    assert {r.sales_rep_user_id for r in (world.db.get(Reseller, world.reseller_a.id),
                                          world.db.get(Reseller, world.reseller_b.id))} == {new_rep.id}
    assert rm.get(f"/replenishment/deliveries/{d['id']}").json()["carried_by"] == "Nova Rep"
    assert rm.get(f"/transfers/{t['id']}").json()["carried_by"] == "Nova Rep"
    assert not next(u for u in rm.get("/users").json() if u["id"] == world.rep.id)["is_active"]
    # Everyone is told.
    titles = [n["title"] for n in world.api(new_rep).get("/notifications").json()]
    assert "You now look after 2 dealer(s): Alpha Tyres, Bravo Auto" in titles
    assert "Your TyreGrow sales rep is now Nova Rep" in [n["title"] for n in world.api(world.user_a).get("/notifications").json()]
    # The new rep can confirm the moved delivery; the old rep cannot sign in.
    world.api(new_rep).post(f"/replenishment/deliveries/{d['id']}/receive", HANDOVER)
    assert world.client.post("/api/auth/login", json={"email": "rep@example.com", "password": "x" * 12}).status_code in (401, 403)
    # The audit entry lists what moved.
    [audit] = rm.get("/audit-events", params={"action": "user.handover"}).json()
    assert audit["summary"].startswith("Handed over from Riley Rep to Nova Rep: 2 dealers (Alpha Tyres, Bravo Auto); "
                                       f"1 delivery ({d['number']}); 1 transfer ({t['number']})")
    assert audit["details"]["dealers"] == sorted([world.reseller_a.id, world.reseller_b.id])
    assert world.api(world.warehouse_op).get("/inventory/reconciliation").json()["balanced"] is True


def test_sharing_moves_only_the_chosen_dealers(world):
    other = make_user(world.db, Role.SALES_REP, "helper@example.com", name="Hana Helper")
    world.db.commit()
    d = _rep_delivery(world)   # to Alpha
    rm = world.api(world.manager)
    rm.post(f"/users/{world.rep.id}/handover", {"to_user_id": other.id, "reseller_ids": [world.reseller_c.id],
                                                "reason": "Sharing"}, expected=422)   # not Riley's dealer
    rm.post(f"/users/{world.rep.id}/handover", {"to_user_id": other.id, "reseller_ids": [world.reseller_b.id],
                                                "deactivate": True, "reason": "Sharing"}, expected=422)
    out = rm.post(f"/users/{world.rep.id}/handover", {"to_user_id": other.id, "reseller_ids": [world.reseller_b.id],
                                                       "reason": "Sharing the north"}).json()
    assert (out["dealers"], out["deliveries"], out["deactivated"]) == (1, 0, False)
    world.db.expire_all()
    assert world.db.get(Reseller, world.reseller_a.id).sales_rep_user_id == world.rep.id
    assert world.db.get(Reseller, world.reseller_b.id).sales_rep_user_id == other.id
    assert rm.get(f"/replenishment/deliveries/{d['id']}").json()["carried_by"] == "Riley Rep"   # Alpha's stays


def test_a_role_mismatch_is_refused(world):
    rm = world.api(world.manager)
    r = rm.post(f"/users/{world.rep.id}/handover", {"to_user_id": world.warehouse_op.id, "reason": "Leaving"},
                expected=422).json()
    assert r["detail"] == "Hand over to someone with the same role (Sales Representative)"
    rm.post(f"/users/{world.rep.id}/handover", {"to_user_id": world.rep.id, "reason": "Leaving"}, expected=422)
    world.api(world.warehouse_op).post(f"/users/{world.rep.id}/handover", {"to_user_id": world.rep.id,
                                                                           "reason": "Leaving"}, expected=403)


def test_deactivating_is_refused_until_everything_is_handed_over(world):
    d = _rep_delivery(world)
    rm = world.api(world.manager)
    r = rm.patch(f"/users/{world.rep.id}", {"is_active": False}, expected=422).json()
    assert r["detail"] == (f"Riley Rep still has 2 dealers (Alpha Tyres, Bravo Auto); 1 delivery ({d['number']}). "
                           "Hand them over first.")
    # An RM waiting on an approval is guarded too.
    set_stock(world.db, world.warehouse, world.p2, 5)
    world.db.commit()
    sr = world.api(world.user_a).post("/stock-requests", {"location_id": world.loc_a.id, "submit": True,
                                                          "lines": [{"product_id": world.p2.id, "quantity": 1}]}).json()
    world.api(world.warehouse_op).post(f"/stock-requests/{sr['id']}/escalate", {"to_user_id": world.manager.id})
    r = world.api(world.admin).patch(f"/users/{world.manager.id}", {"is_active": False}, expected=422).json()
    assert f"1 approval ({sr['number']})" in r["detail"]
    # Hand the approval to another RM: it can then be decided by them, and deactivation goes through.
    world.api(world.admin).post(f"/users/{world.manager.id}/handover", {"to_user_id": world.finance.id,
                                                                        "reason": "Moving on"})
    world.api(world.finance).post(f"/stock-requests/{sr['id']}/decision", {
        "lines": [{"line_id": sr["lines"][0]["id"], "approve_qty": 1}], "approval": APPROVAL})
    world.api(world.admin).patch(f"/users/{world.manager.id}", {"is_active": False})
    # A user with nothing open can be deactivated straight away.
    idle = make_user(world.db, Role.SALES_REP, "idle@example.com")
    world.db.commit()
    world.api(world.admin).patch(f"/users/{idle.id}", {"is_active": False})


def test_a_new_user_can_replace_someone_in_one_step(world):
    rm = world.api(world.manager)
    body = {"email": "replacement@example.com", "full_name": "Rae Replacement", "password": "first-pass-123",
            "role": "SALES_REP", "replaces": {"user_id": world.rep.id, "mode": "TAKE_OVER"}}
    rm.post("/users", {**body, "role": "WAREHOUSE_MANAGER"}, expected=422)   # different role: nothing is created
    assert not any(u["email"] == "replacement@example.com" for u in rm.get("/users").json())
    new = rm.post("/users", body, expected=201).json()
    world.db.expire_all()
    assert world.db.get(Reseller, world.reseller_a.id).sales_rep_user_id == new["id"]
    assert not next(u for u in rm.get("/users").json() if u["id"] == world.rep.id)["is_active"]
    # Sharing: the next person works alongside Rae on one dealer.
    shared = rm.post("/users", {**body, "email": "share@example.com", "full_name": "Sam Share",
                                "replaces": {"user_id": new["id"], "mode": "SHARE",
                                             "reseller_ids": [world.reseller_b.id]}}, expected=201).json()
    world.db.expire_all()
    assert world.db.get(Reseller, world.reseller_b.id).sales_rep_user_id == shared["id"]
    assert world.db.get(Reseller, world.reseller_a.id).sales_rep_user_id == new["id"]
