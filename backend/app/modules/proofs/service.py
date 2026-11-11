"""Proof of receipt: who may confirm a delivery or transfer, what a Sales Rep must record, and drop-off photos.

Photos are compressed on the phone before upload (about 1280 px, medium JPEG quality: ~100–250 KB) and kept in the
database. Limits keep storage predictable: at most MAX_PHOTOS per delivery/transfer, MAX_BYTES each.
"""

import base64
import binascii
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.core.industry import vocab
from app.core.permissions import P, Role, role_has
from app.modules.identity.models import User
from app.modules.proofs.models import AppSetting, ProofPhoto

MAX_PHOTOS = 3
DELETE_AFTER_ARCHIVE_DAYS = 90
ARCHIVE_KEY = "photo_archive"
DEFAULT_ARCHIVE = {"value": 6, "unit": "months"}   # None value = never archive
_ACTIVE = (ProofPhoto.archived_at.is_(None), ProofPhoto.deleted_at.is_(None))
MAX_BYTES = 600 * 1024
TYPES = {"image/jpeg": b"\xff\xd8\xff", "image/webp": b"RIFF"}


def _carrier_name(db: Session, user_id: int | None) -> str:
    u = db.get(User, user_id) if user_id else None
    return u.full_name if u else "the sales representative"


def ensure_can_confirm(db: Session, actor: User, *, reseller_id: int, carried_by_user_id: int | None, what: str) -> None:
    """Stock carried by a Sales Rep is confirmed only by the receiving dealer or that Sales Rep."""
    if actor.is_reseller_user:
        if actor.reseller_id != reseller_id:
            raise NotFoundError(f"{what} not found")
        return
    if carried_by_user_id is not None and actor.id != carried_by_user_id:
        raise PermissionDeniedError(
            f"{_carrier_name(db, carried_by_user_id)} is carrying this {what.lower()}: only the {vocab.partner} or "
            f"{_carrier_name(db, carried_by_user_id)} can confirm it was received")


def receipt_details(actor: User, received_by_name: str | None, notes: str | None) -> tuple[str | None, str | None]:
    """A Sales Rep confirming a hand-over must say who took the stock and add a short note."""
    name = (received_by_name or "").strip() or None
    text = (notes or "").strip() or None
    if actor.role == Role.SALES_REP:
        if not name or len(name) < 2:
            raise BusinessRuleError(f"Enter the name of the person at the {vocab.partner} who received the stock")
        if not text or len(text) < 3:
            raise BusinessRuleError("Add a short note about the hand-over (who was there, anything to remember)")
    return name, text


# ---------------------------------------------------------------- photos
def _entity(db: Session, entity_type: str, entity_id: int):
    from app.modules.replenishment.models import Delivery
    from app.modules.transfers.models import Transfer

    model = {"delivery": Delivery, "transfer": Transfer}.get(entity_type)
    obj = db.get(model, entity_id) if model else None
    if obj is None:
        raise NotFoundError("Record not found")
    reseller_id = obj.reseller_id if entity_type == "delivery" else obj.destination_reseller_id
    return obj, reseller_id


def _can_see(user: User, entity_type: str, reseller_id: int, obj) -> bool:
    if user.is_reseller_user:
        if entity_type == "transfer":
            return user.reseller_id in (obj.destination_reseller_id, obj.source_reseller_id)
        return user.reseller_id == reseller_id
    return role_has(user.role, P.INVENTORY_READ)


def add_photo(db: Session, actor: User, entity_type: str, entity_id: int, data_url: str) -> ProofPhoto:
    obj, reseller_id = _entity(db, entity_type, entity_id)
    if actor.is_reseller_user:
        if actor.reseller_id != reseller_id:
            raise NotFoundError("Record not found")
    elif not role_has(actor.role, P.DELIVERY_CONFIRM if entity_type == "delivery" else P.TRANSFER_EXECUTE):
        raise PermissionDeniedError("You cannot add photos to this record")
    try:
        header, b64 = data_url.split(",", 1)
        content_type = header.removeprefix("data:").split(";")[0]
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise BusinessRuleError("The photo could not be read; please take it again") from exc
    magic = TYPES.get(content_type)
    if magic is None or not raw.startswith(magic) or (content_type == "image/webp" and raw[8:12] != b"WEBP"):
        raise BusinessRuleError("Only JPEG or WebP photos can be added")
    if len(raw) > MAX_BYTES:
        raise BusinessRuleError(f"The photo is too large ({len(raw) // 1024} KB); the limit is {MAX_BYTES // 1024} KB")
    count = len(db.execute(select(ProofPhoto.id).where(ProofPhoto.entity_type == entity_type,
                                                       ProofPhoto.entity_id == entity_id, *_ACTIVE)).all())
    if count >= MAX_PHOTOS:
        raise BusinessRuleError(f"Up to {MAX_PHOTOS} photos can be added")
    photo = ProofPhoto(entity_type=entity_type, entity_id=entity_id, content_type=content_type, size_bytes=len(raw),
                       data=raw, taken_by_user_id=actor.id)
    db.add(photo)
    db.flush()
    return photo


def get_photo(db: Session, user: User, photo_id: int) -> ProofPhoto:
    photo = db.get(ProofPhoto, photo_id)
    if photo is None or photo.deleted_at is not None or photo.data is None:
        raise NotFoundError("Photo not found")
    if photo.archived_at is not None:   # archived: only RM / Admin can still open it, until it is deleted
        if not role_has(user.role, P.SETTINGS_MANAGE):
            raise NotFoundError("Photo not found")
        return photo
    obj, reseller_id = _entity(db, photo.entity_type, photo.entity_id)
    if not _can_see(user, photo.entity_type, reseller_id, obj):
        raise NotFoundError("Photo not found")
    return photo


def photo_ids(db: Session, entity_type: str, ids) -> dict[int, list[int]]:
    """{entity_id: [photo ids]} without loading the image bytes."""
    wanted = {i for i in ids if i is not None}
    out: dict[int, list[int]] = {i: [] for i in wanted}
    if wanted:
        for pid, eid in db.execute(select(ProofPhoto.id, ProofPhoto.entity_id).where(
                ProofPhoto.entity_type == entity_type, ProofPhoto.entity_id.in_(wanted), *_ACTIVE)
                .order_by(ProofPhoto.id)):
            out[eid].append(pid)
    return out


def first_photo(db: Session, entity_type: str, entity_id: int) -> bytes | None:
    row = db.execute(select(ProofPhoto.data).where(ProofPhoto.entity_type == entity_type,
                                                   ProofPhoto.entity_id == entity_id, *_ACTIVE)
                     .order_by(ProofPhoto.id).limit(1)).scalar_one_or_none()
    return row


def retired_counts(db: Session, entity_type: str, ids) -> dict[int, int]:
    """{entity_id: number of photos archived or deleted} so screens can say a photo was retired."""
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = db.execute(select(ProofPhoto.entity_id, func.count()).where(
        ProofPhoto.entity_type == entity_type, ProofPhoto.entity_id.in_(wanted),
        (ProofPhoto.archived_at.is_not(None)) | (ProofPhoto.deleted_at.is_not(None))).group_by(ProofPhoto.entity_id))
    return dict(rows.all())


# ---------------------------------------------------------------- archiving (retention)
def archive_policy(db: Session) -> dict:
    row = db.get(AppSetting, ARCHIVE_KEY)
    return dict(row.value) if row else dict(DEFAULT_ARCHIVE)


def archive_after(policy: dict) -> timedelta | None:
    value = policy.get("value")
    if not value:
        return None
    return timedelta(days=int(value) * (30 if policy.get("unit") == "months" else 1))


def set_archive_policy(db: Session, actor: User, value: int | None, unit: str) -> dict:
    if unit not in ("days", "months"):
        raise BusinessRuleError("Choose days or months")
    if value is not None and not (1 <= value <= (120 if unit == "months" else 3650)):
        raise BusinessRuleError("Choose between 1 and 120 months, or 1 and 3650 days")
    policy = {"value": value, "unit": unit}
    row = db.get(AppSetting, ARCHIVE_KEY)
    if row is None:
        db.add(AppSetting(key=ARCHIVE_KEY, value=policy, updated_by_user_id=actor.id))
    else:
        row.value, row.updated_by_user_id = policy, actor.id
    from app.modules.audit.service import record_audit

    record_audit(db, actor_id=actor.id, action="settings.photo_archive", entity_type="setting", entity_id=None,
                 summary="Photo archiving: " + (f"archive after {value} {unit}" if value else "off"))
    db.flush()
    return policy


def run_retention(db: Session, now: datetime | None = None) -> dict:
    """Archive photos older than the configured period; delete photos archived 90+ days ago. Safe to run often."""
    now = now or datetime.now(UTC)
    after = archive_after(archive_policy(db))
    archived = 0
    if after is not None:
        archived = db.execute(update(ProofPhoto).where(*_ACTIVE, ProofPhoto.created_at < now - after)
                              .values(archived_at=now)).rowcount
    deleted = db.execute(update(ProofPhoto).where(
        ProofPhoto.deleted_at.is_(None), ProofPhoto.archived_at < now - timedelta(days=DELETE_AFTER_ARCHIVE_DAYS))
        .values(deleted_at=now, data=None)).rowcount
    db.flush()
    return {"archived": archived, "deleted": deleted, "ran_at": now}


def archive_stats(db: Session) -> dict:
    def agg(*where):
        n, size = db.execute(select(func.count(), func.coalesce(func.sum(ProofPhoto.size_bytes), 0)).where(*where)).one()
        return int(n), int(size)

    active, active_bytes = agg(*_ACTIVE)
    archived, archived_bytes = agg(ProofPhoto.archived_at.is_not(None), ProofPhoto.deleted_at.is_(None))
    deleted, _ = agg(ProofPhoto.deleted_at.is_not(None))
    next_archive = db.execute(select(func.min(ProofPhoto.created_at)).where(*_ACTIVE)).scalar_one()
    next_delete = db.execute(select(func.min(ProofPhoto.archived_at)).where(
        ProofPhoto.archived_at.is_not(None), ProofPhoto.deleted_at.is_(None))).scalar_one()
    after = archive_after(archive_policy(db))
    return {
        "active": active, "active_kb": active_bytes // 1024, "archived": archived, "archived_kb": archived_bytes // 1024,
        "deleted": deleted,
        "next_archive_on": (next_archive + after) if next_archive and after else None,
        "next_delete_on": (next_delete + timedelta(days=DELETE_AFTER_ARCHIVE_DAYS)) if next_delete else None,
    }


def archived_photos(db: Session, limit: int = 200) -> list[dict]:
    from app.modules.replenishment.models import Delivery
    from app.modules.transfers.models import Transfer

    rows = db.execute(select(ProofPhoto.id, ProofPhoto.entity_type, ProofPhoto.entity_id, ProofPhoto.size_bytes,
                             ProofPhoto.created_at, ProofPhoto.archived_at)
                      .where(ProofPhoto.archived_at.is_not(None), ProofPhoto.deleted_at.is_(None))
                      .order_by(ProofPhoto.archived_at, ProofPhoto.id).limit(limit)).all()
    numbers = {}
    for kind, model in (("delivery", Delivery), ("transfer", Transfer)):
        ids = {r.entity_id for r in rows if r.entity_type == kind}
        if ids:
            numbers.update({(kind, i): n for i, n in db.execute(select(model.id, model.number).where(model.id.in_(ids)))})
    return [{
        "id": r.id, "entity_type": r.entity_type, "entity_id": r.entity_id, "number": numbers.get((r.entity_type, r.entity_id)),
        "size_kb": r.size_bytes // 1024, "taken_at": r.created_at, "archived_at": r.archived_at,
        "delete_on": r.archived_at + timedelta(days=DELETE_AFTER_ARCHIVE_DAYS),
    } for r in rows]
