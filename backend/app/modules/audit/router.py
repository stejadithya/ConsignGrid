from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.core.permissions import P
from app.modules.audit.models import AuditEvent
from app.modules.identity.deps import DB, require
from app.modules.identity.models import User

router = APIRouter(tags=["audit"])


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    actor_user_id: int | None
    actor_name: str | None = None
    action: str
    entity_type: str
    entity_id: int | None
    reseller_id: int | None
    summary: str
    details: dict | None


@router.get("/audit-events", response_model=list[AuditEventOut])
def list_audit_events(
    db: DB, _: Annotated[User, Depends(require(P.AUDIT_READ))],
    action: str | None = None, entity_type: str | None = None, entity_id: int | None = None,
    reseller_id: int | None = None, actor_user_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100, offset: Annotated[int, Query(ge=0)] = 0,
):
    stmt = select(AuditEvent, User.full_name).outerjoin(User, User.id == AuditEvent.actor_user_id)
    if action:
        stmt = stmt.where(AuditEvent.action.ilike(f"{action}%"))
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    if reseller_id is not None:
        stmt = stmt.where(AuditEvent.reseller_id == reseller_id)
    if actor_user_id is not None:
        stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)
    rows = db.execute(stmt.order_by(AuditEvent.id.desc()).limit(limit).offset(offset)).tuples()
    out = []
    for ev, name in rows:
        o = AuditEventOut.model_validate(ev)
        o.actor_name = name
        out.append(o)
    return out
