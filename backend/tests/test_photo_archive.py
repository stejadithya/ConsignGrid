"""Drop-off photo archiving: configurable period, archived photos visible to RM/Admin only, deleted 90 days later."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.core.config import get_settings
from app.core.permissions import Role
from app.modules.proofs.models import ProofPhoto
from tests.factories import HANDOVER, make_user
from tests.test_receipt_proof import _photo, _rep_delivery


def _delivery_with_photo(world):
    d = _rep_delivery(world)
    return world.api(world.rep).post(f"/replenishment/deliveries/{d['id']}/receive",
                                     {**HANDOVER, "photos": [_photo()]}).json()


def _age(world, photo_id, *, created_days=0, archived_days=None):
    now = datetime.now(UTC)
    values = {"created_at": now - timedelta(days=created_days)}
    if archived_days is not None:
        values["archived_at"] = now - timedelta(days=archived_days)
    world.db.execute(update(ProofPhoto).where(ProofPhoto.id == photo_id).values(**values))
    world.db.commit()


def test_setting_defaults_to_six_months_and_only_rm_admin_change_it(world):
    rm = world.api(world.manager)
    s = rm.get("/proofs/archive-settings").json()
    assert (s["value"], s["unit"], s["delete_after_archive_days"]) == (6, "months", 90)
    for u in (world.warehouse_op, world.rep, world.user_a):
        world.api(u).put("/proofs/archive-settings", {"value": 3, "unit": "months"}, expected=403)
    rm.put("/proofs/archive-settings", {"value": 200, "unit": "months"}, expected=422)
    s = rm.put("/proofs/archive-settings", {"value": 45, "unit": "days"}).json()
    assert (s["value"], s["unit"]) == (45, "days")
    admin = make_user(world.db, Role.ADMINISTRATOR, "super@example.com")
    world.db.commit()
    world.api(admin).put("/proofs/archive-settings", {"value": None, "unit": "months"}, expected=200)


def test_archive_then_delete_after_90_days(world):
    d = _delivery_with_photo(world)
    pid = d["photos"][0]
    rm = world.api(world.manager)
    _age(world, pid, created_days=100)
    assert rm.post("/proofs/retention/run").json()["archived"] == 0          # younger than 6 months
    _age(world, pid, created_days=200)
    assert rm.post("/proofs/retention/run").json()["archived"] == 1
    # Hidden from normal screens; RM / Admin can still open it from the archive list.
    d = world.api(world.user_a).get("/replenishment/deliveries").json()[0]
    assert d["photos"] == [] and d["photos_retired"] == 1
    world.api(world.user_a).get(f"/proofs/photos/{pid}", expected=404)
    world.api(world.warehouse_op).get(f"/proofs/photos/{pid}", expected=404)
    rm.get(f"/proofs/photos/{pid}", expected=200)
    [a] = rm.get("/proofs/archived").json()
    assert a["id"] == pid and a["number"] == d["number"]
    pdf = world.api(world.user_a).get(f"/replenishment/deliveries/{d['id']}/delivery-note.pdf").content
    assert b"/Subtype /Image" not in pdf
    # 90 days after archiving the photo itself is deleted; the record (who received it) stays.
    _age(world, pid, created_days=300, archived_days=89)
    assert rm.post("/proofs/retention/run").json()["deleted"] == 0
    _age(world, pid, created_days=300, archived_days=91)
    assert rm.post("/proofs/retention/run").json()["deleted"] == 1
    rm.get(f"/proofs/photos/{pid}", expected=404)
    assert rm.get("/proofs/archived").json() == []
    s = rm.get("/proofs/archive-settings").json()
    assert (s["active"], s["archived"], s["deleted"]) == (0, 0, 1)
    d = world.api(world.user_a).get("/replenishment/deliveries").json()[0]
    assert d["received_by_name"] == HANDOVER["received_by_name"] and d["photos_retired"] == 1


def test_archiving_off_keeps_photos(world):
    d = _delivery_with_photo(world)
    rm = world.api(world.manager)
    rm.put("/proofs/archive-settings", {"value": None, "unit": "months"})
    _age(world, d["photos"][0], created_days=2000)
    assert rm.post("/proofs/retention/run").json()["archived"] == 0


def test_daily_cron_needs_the_secret(world, monkeypatch):
    client = world.client
    assert client.get("/api/proofs/retention/cron").status_code == 403          # no secret configured
    monkeypatch.setattr(get_settings(), "cron_secret", "s3cret-value-for-cron")
    assert client.get("/api/proofs/retention/cron", headers={"Authorization": "Bearer wrong"}).status_code == 403
    r = client.get("/api/proofs/retention/cron", headers={"Authorization": "Bearer s3cret-value-for-cron"})
    assert r.status_code == 200 and r.json()["archived"] == 0
