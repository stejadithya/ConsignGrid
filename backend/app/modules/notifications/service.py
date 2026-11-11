"""In-app notifications (the bell). Any module may notify users; each user only ever sees their own."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import P, Role, role_has
from app.modules.identity.models import User
from app.modules.stock_requests.models import Notification


def notify_users(db: Session, user_ids: Iterable[int | None], title: str, body: str | None, *, link: str | None,
                 entity_type: str | None = None, entity_id: int | None = None, exclude: int | None = None) -> None:
    for uid in sorted({u for u in user_ids if u is not None} - {exclude}):
        db.add(Notification(user_id=uid, title=title[:200], body=body, link=link, entity_type=entity_type,
                            entity_id=entity_id))


def staff_with(db: Session, perm: P) -> list[int]:
    """Active dealership staff whose role holds the permission."""
    roles = [r.value for r in Role if role_has(r, perm) and r != Role.RESELLER]
    return list(db.execute(select(User.id).where(User.role.in_(roles), User.is_active.is_(True))).scalars())


def staff_in_roles(db: Session, *roles: Role) -> list[int]:
    return list(db.execute(select(User.id).where(User.role.in_([r.value for r in roles]),
                                                 User.is_active.is_(True))).scalars())


def reseller_users(db: Session, reseller_id: int) -> list[int]:
    return list(db.execute(select(User.id).where(User.reseller_id == reseller_id, User.is_active.is_(True))).scalars())
