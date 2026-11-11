from typing import Any

from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent


def record_audit(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    summary: str,
    reseller_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        reseller_id=reseller_id,
        summary=summary,
        details=details,
    )
    db.add(event)
    return event
