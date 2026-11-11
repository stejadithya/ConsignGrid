"""Phase 2: inventory ledger invariants, constraints, concurrency and reconciliation."""

import threading

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.db import session_factory
from app.core.errors import InsufficientStockError
from app.modules.customers.models import Location, LocationType
from app.modules.inventory.models import (
    InventoryEntry,
    ReservationPurpose,
    ReservationStatus,
    StockReservation,
    TxnType,
)
from app.modules.inventory.service import Ledger, reconcile, system_location, unbalanced_transactions
from tests.factories import set_stock


def test_opening_balance_via_api_creates_ledger_and_balance(world):
    api = world.api(world.warehouse_op)
    txn = api.post("/inventory/opening-balances", {
        "location_id": world.warehouse.id,
        "lines": [{"product_id": world.p1.id, "quantity": 100}, {"product_id": world.p2.id, "quantity": 40}],
    }, expected=201).json()
    assert txn["txn_type"] == "OPENING_BALANCE"
    assert sum(e["quantity"] for e in txn["entries"]) == 0  # double entry
    assert world.bal(world.warehouse, world.p1).on_hand == 100
    assert world.bal(world.warehouse, world.p2).on_hand == 40
    rows = api.get("/inventory/balances", params={"location_id": world.warehouse.id}).json()
    assert {(r["sku"], r["available"]) for r in rows} == {("TYR-001", 100), ("TYR-002", 40)}


def test_adjustment_requires_permission_and_reason(world):
    set_stock(world.db, world.warehouse, world.p1, 10)
    world.db.commit()
    body = {"location_id": world.warehouse.id, "product_id": world.p1.id, "quantity_delta": -3, "reason": "Damaged in handling"}
    world.api(world.rep).post("/inventory/adjustments", body, expected=403)
    world.api(world.warehouse_op).post("/inventory/adjustments", {**body, "reason": ""}, expected=422)
    txn = world.api(world.warehouse_op).post("/inventory/adjustments", body, expected=201).json()
    assert txn["approved_by_user_id"] == world.warehouse_op.id
    assert world.bal(world.warehouse, world.p1).on_hand == 7
    # The Relationship Manager has every Warehouse Manager permission (P-028), with the same reason rule.
    world.api(world.manager).post("/inventory/adjustments", {**body, "reason": ""}, expected=422)
    txn = world.api(world.manager).post("/inventory/adjustments", body, expected=201).json()
    assert txn["approved_by_user_id"] == world.manager.id
    assert world.bal(world.warehouse, world.p1).on_hand == 4


def test_negative_stock_is_rejected(world):
    set_stock(world.db, world.warehouse, world.p1, 5)
    world.db.commit()
    body = {"location_id": world.warehouse.id, "product_id": world.p1.id, "quantity_delta": -6, "reason": "Too many"}
    r = world.api(world.warehouse_op).post("/inventory/adjustments", body, expected=409)
    assert r.json()["code"] == "insufficient_stock"
    assert world.bal(world.warehouse, world.p1).on_hand == 5


def test_block_unblock_and_write_off(world):
    set_stock(world.db, world.warehouse, world.p1, 10)
    world.db.commit()
    op, rm = world.api(world.warehouse_op), world.api(world.manager)
    base = {"location_id": world.warehouse.id, "product_id": world.p1.id, "reason": "Sidewall damage"}
    op.post("/inventory/block", {**base, "quantity": 3}, expected=201)
    b = world.bal(world.warehouse, world.p1)
    assert (b.on_hand, b.blocked, b.available) == (10, 3, 7)
    op.post("/inventory/unblock", {**base, "quantity": 1}, expected=201)
    world.api(world.rep).post("/inventory/write-offs", {**base, "quantity": 1}, expected=403)  # needs inventory.adjust
    rm.post("/inventory/write-offs", {**base, "quantity": 1}, expected=201)  # the RM has it too (P-028)
    op.post("/inventory/write-offs", {**base, "quantity": 1}, expected=201)
    b = world.bal(world.warehouse, world.p1)
    assert (b.on_hand, b.blocked, b.available) == (8, 0, 8)
    # Cannot block more than available.
    op.post("/inventory/block", {**base, "quantity": 9}, expected=409)


def test_reserve_move_release_keeps_buckets_consistent(world, db):
    set_stock(db, world.warehouse, world.p1, 10)
    transit = system_location(db, LocationType.TRANSIT)
    led = Ledger(db, TxnType.RESERVATION, actor_id=world.manager.id)
    res = led.reserve(world.warehouse, world.p1.id, 6, ReservationPurpose.REPLENISHMENT)
    b = world.bal(world.warehouse, world.p1)
    assert (b.on_hand, b.reserved, b.available) == (10, 6, 4)

    # Reserved stock cannot be taken by an unreserved movement beyond availability.
    with pytest.raises(InsufficientStockError):
        Ledger(db, TxnType.ADJUSTMENT, actor_id=None).move(
            world.p1.id, world.warehouse, system_location(db, LocationType.ADJUSTMENT), 5)

    Ledger(db, TxnType.REPLENISHMENT_DISPATCH, actor_id=None).move(
        world.p1.id, world.warehouse, transit, 4, reservation=res)
    Ledger(db, TxnType.RESERVATION_RELEASE, actor_id=None).release(res)
    db.commit()
    db.refresh(res)
    assert (res.consumed_qty, res.released_qty, res.status) == (4, 2, ReservationStatus.CLOSED)
    b = world.bal(world.warehouse, world.p1)
    assert (b.on_hand, b.reserved, b.available) == (6, 0, 6)
    assert world.bal(transit, world.p1).on_hand == 4
    assert reconcile(db) == []
    assert unbalanced_transactions(db) == []


def test_database_constraint_is_final_backstop(world, db):
    """Even a buggy direct UPDATE cannot make available stock negative."""
    set_stock(db, world.warehouse, world.p1, 3)
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE stock_balances SET reserved = 4 WHERE location_id = :l AND product_id = :p"),
                   {"l": world.warehouse.id, "p": world.p1.id})
        db.flush()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE stock_balances SET on_hand = -1 WHERE location_id = :l"), {"l": world.warehouse.id})
    db.rollback()


def test_concurrent_reservations_cannot_over_allocate(world, db):
    """Acceptance test 5: two employees try to allocate the same remaining warehouse quantity."""
    set_stock(db, world.warehouse, world.p1, 5)
    db.commit()
    wh_id, p_id = world.warehouse.id, world.p1.id

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def attempt():
        s = session_factory()()
        try:
            wh = s.get(Location, wh_id)
            barrier.wait()
            led = Ledger(s, TxnType.RESERVATION, actor_id=None)
            led.reserve(wh, p_id, 4, ReservationPurpose.REPLENISHMENT)
            s.commit()
            with lock:
                results.append("ok")
        except InsufficientStockError:
            s.rollback()
            with lock:
                results.append("rejected")
        finally:
            s.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(results) == ["ok", "rejected"]
    b = world.bal(world.warehouse, world.p1)
    assert (b.on_hand, b.reserved, b.available) == (5, 4, 1)
    active = db.execute(select(StockReservation).where(StockReservation.status == ReservationStatus.ACTIVE)).scalars().all()
    assert len(active) == 1 and active[0].quantity == 4
    assert reconcile(db) == []


def test_many_concurrent_small_reservations_never_exceed_stock(world, db):
    set_stock(db, world.warehouse, world.p2, 10)
    db.commit()
    wh_id, p_id = world.warehouse.id, world.p2.id
    ok = []

    def attempt():
        s = session_factory()()
        try:
            led = Ledger(s, TxnType.RESERVATION, actor_id=None)
            led.reserve(s.get(Location, wh_id), p_id, 3, ReservationPurpose.REPLENISHMENT)
            s.commit()
            ok.append(1)
        except InsufficientStockError:
            s.rollback()
        finally:
            s.close()

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert len(ok) == 3  # 3 × 3 = 9 ≤ 10; a 4th would exceed
    b = world.bal(world.warehouse, world.p2)
    assert b.reserved == 9 and b.available == 1


def test_reconciliation_rebuilds_balances_from_history(world, db):
    """Acceptance test 8: rebuild a location's position from its movement history."""
    api = world.api(world.warehouse_op)
    api.post("/inventory/opening-balances", {"location_id": world.loc_a.id,
                                             "lines": [{"product_id": world.p1.id, "quantity": 20}]})
    api.post("/inventory/adjustments", {"location_id": world.loc_a.id, "product_id": world.p1.id,
                                        "quantity_delta": -2, "reason": "Count correction"})
    api.post("/inventory/block", {"location_id": world.loc_a.id, "product_id": world.p1.id, "quantity": 1,
                                  "reason": "Puncture"})
    rec = api.get("/inventory/reconciliation", params={"location_id": world.loc_a.id}).json()
    assert rec["balanced"] is True and rec["differences"] == []

    # Manually rebuild from entries and compare.
    entries = db.execute(select(InventoryEntry).where(InventoryEntry.location_id == world.loc_a.id)).scalars().all()
    rebuilt = {"ON_HAND": 0, "RESERVED": 0, "BLOCKED": 0}
    for e in entries:
        rebuilt[e.bucket.value] += e.quantity
    b = world.bal(world.loc_a, world.p1)
    assert rebuilt == {"ON_HAND": b.on_hand, "RESERVED": b.reserved, "BLOCKED": b.blocked} == \
        {"ON_HAND": 18, "RESERVED": 0, "BLOCKED": 1}

    # Tampering with the projection is detected.
    db.execute(text("UPDATE stock_balances SET on_hand = on_hand + 1 WHERE location_id = :l"), {"l": world.loc_a.id})
    db.commit()
    rec = api.get("/inventory/reconciliation").json()
    assert rec["balanced"] is False
    assert rec["differences"][0]["ledger_qty"] == 18 and rec["differences"][0]["balance_qty"] == 19


def test_reseller_user_sees_only_own_balances(world):
    set_stock(world.db, world.loc_a, world.p1, 6)
    set_stock(world.db, world.loc_b, world.p1, 9)
    world.db.commit()
    rows = world.api(world.user_a).get("/inventory/balances").json()
    assert {r["location_code"] for r in rows} == {"RA-MAIN"}
    # Explicitly asking for another reseller's location returns nothing.
    assert world.api(world.user_a).get("/inventory/balances", params={"location_id": world.loc_b.id}).json() == []
    world.api(world.user_a).get(f"/resellers/{world.reseller_b.id}", expected=404)
    world.api(world.user_a).get(f"/resellers/{world.reseller_a.id}", expected=200)
    world.api(world.user_a).get("/inventory/reconciliation", expected=403)
    world.api(world.user_a).get(f"/inventory/availability/{world.p1.id}", expected=403)
    assert [r["account_ref"] for r in world.api(world.user_a).get("/resellers").json()] == ["RA"]
