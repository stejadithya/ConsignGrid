import hmac
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.errors import PermissionDeniedError
from app.core.permissions import P
from app.modules.identity.deps import DB, CurrentUser, require
from app.modules.identity.models import User
from app.modules.proofs import service

router = APIRouter(prefix="/proofs", tags=["proof of receipt"])


class PhotoIn(BaseModel):
    data_url: str = Field(max_length=900_000)   # base64 of a compressed photo (~600 KB max)


class PhotoOut(BaseModel):
    id: int
    size_bytes: int


@router.post("/{entity_type}/{entity_id}/photos", response_model=PhotoOut, status_code=201)
def add_photo(entity_type: Literal["delivery", "transfer"], entity_id: int, data: PhotoIn, db: DB,
              user: Annotated[User, Depends(require(P.INVENTORY_READ))]):
    """Add a drop-off photo (taken and compressed on the phone)."""
    photo = service.add_photo(db, user, entity_type, entity_id, data.data_url)
    db.commit()
    return PhotoOut(id=photo.id, size_bytes=photo.size_bytes)


@router.get("/photos/{photo_id}")
def get_photo(photo_id: int, db: DB, user: CurrentUser):
    photo = service.get_photo(db, user, photo_id)
    return Response(content=photo.data, media_type=photo.content_type,
                    headers={"Cache-Control": "private, max-age=86400"})


Manager = Annotated[User, Depends(require(P.SETTINGS_MANAGE))]


class ArchivePolicyIn(BaseModel):
    value: int | None = Field(default=None, ge=1)   # empty = never archive
    unit: Literal["days", "months"] = "months"


class ArchiveOut(BaseModel):
    value: int | None
    unit: str
    delete_after_archive_days: int
    active: int
    active_kb: int
    archived: int
    archived_kb: int
    deleted: int
    next_archive_on: datetime | None
    next_delete_on: datetime | None


class ArchivedPhotoOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    number: str | None
    size_kb: int
    taken_at: datetime
    archived_at: datetime
    delete_on: datetime


class RetentionOut(BaseModel):
    archived: int
    deleted: int
    ran_at: datetime


def _archive_out(db) -> ArchiveOut:
    return ArchiveOut(**service.archive_policy(db), delete_after_archive_days=service.DELETE_AFTER_ARCHIVE_DAYS,
                      **service.archive_stats(db))


@router.get("/archive-settings", response_model=ArchiveOut)
def archive_settings(db: DB, user: Manager):
    return _archive_out(db)


@router.put("/archive-settings", response_model=ArchiveOut)
def set_archive_settings(data: ArchivePolicyIn, db: DB, user: Manager):
    service.set_archive_policy(db, user, data.value, data.unit)
    db.commit()
    return _archive_out(db)


@router.get("/archived", response_model=list[ArchivedPhotoOut])
def archived(db: DB, user: Manager):
    """Archived photos (hidden from normal screens) that RM / Admin can still open until they are deleted."""
    return service.archived_photos(db)


@router.post("/retention/run", response_model=RetentionOut)
def run_now(db: DB, user: Manager):
    out = service.run_retention(db)
    db.commit()
    return out


@router.get("/retention/cron", response_model=RetentionOut, include_in_schema=False)
def cron(db: DB, authorization: Annotated[str | None, Header()] = None):
    """Daily clean-up called by Vercel Cron with "Authorization: Bearer <CRON_SECRET>"."""
    secret = get_settings().cron_secret
    if not secret or not hmac.compare_digest(authorization or "", f"Bearer {secret}"):
        raise PermissionDeniedError("Not allowed")
    out = service.run_retention(db)
    db.commit()
    return out
