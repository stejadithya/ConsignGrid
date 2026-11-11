"""Pilot support: user feedback and reference documents."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.errors import NotFoundError
from app.core.permissions import STAFF_ROLES, P, Role
from app.modules.audit.service import record_audit
from app.modules.identity.deps import DB, CurrentUser, require
from app.modules.identity.models import User
from app.modules.pilot.models import FeedbackType, PilotFeedback
from app.modules.pilot.reference import asset_dir, get_document, list_documents

router = APIRouter(tags=["pilot"])


class FeedbackIn(BaseModel):
    page: str = Field(min_length=1, max_length=200)
    feedback_type: FeedbackType
    description: str = Field(min_length=3, max_length=5000)


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    user_name: str | None = None
    role: str
    page: str
    feedback_type: FeedbackType
    description: str
    created_at: datetime


@router.post("/feedback", response_model=FeedbackOut, status_code=201)
def submit_feedback(data: FeedbackIn, db: DB, user: Annotated[User, Depends(require(P.FEEDBACK_SUBMIT))]):
    fb = PilotFeedback(user_id=user.id, role=str(user.role), page=data.page.strip(), feedback_type=data.feedback_type,
                       description=data.description.strip())
    db.add(fb)
    db.flush()
    record_audit(db, actor_id=user.id, action="feedback.submit", entity_type="pilot_feedback", entity_id=fb.id,
                 summary=f"Pilot feedback ({fb.feedback_type}) on {fb.page}")
    db.commit()
    return FeedbackOut.model_validate(fb).model_copy(update={"user_name": user.full_name})


@router.get("/feedback", response_model=list[FeedbackOut])
def list_feedback(db: DB, _: Annotated[User, Depends(require(P.AUDIT_READ))],
                  limit: Annotated[int, Query(ge=1, le=1000)] = 500):
    rows = db.execute(select(PilotFeedback, User.full_name).join(User, User.id == PilotFeedback.user_id)
                      .order_by(PilotFeedback.created_at.desc(), PilotFeedback.id.desc()).limit(limit)).all()
    return [FeedbackOut.model_validate(fb).model_copy(update={"user_name": name}) for fb, name in rows]


class ReferenceDocumentOut(BaseModel):
    id: str
    title: str
    description: str
    effective_date: date
    media_type: str
    width: int
    height: int
    url: str


def _staff_only(user: User) -> None:
    # Dealer price lists are internal to the dealership; reseller users get "not found" (no information leak).
    if Role(user.role) not in STAFF_ROLES:
        raise NotFoundError("Document not found")


@router.get("/reference-documents", response_model=list[ReferenceDocumentOut])
def list_reference_documents(user: CurrentUser):
    if Role(user.role) not in STAFF_ROLES:
        return []
    return [ReferenceDocumentOut(id=d.id, title=d.title, description=d.description, effective_date=d.effective_date,
                                 media_type=d.media_type, width=d.width, height=d.height,
                                 url=f"/api/reference-documents/{d.id}/file") for d in list_documents()]


@router.get("/reference-documents/{doc_id}/file")
def reference_document_file(doc_id: str, user: CurrentUser):
    _staff_only(user)
    doc = get_document(doc_id)
    path = asset_dir() / doc.filename if doc else None
    if doc is None or not path.is_file():
        raise NotFoundError("Document not found")
    return FileResponse(path, media_type=doc.media_type, headers={"Cache-Control": "private, max-age=3600"})
