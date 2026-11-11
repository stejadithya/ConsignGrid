import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import flush_or_conflict
from app.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.core.permissions import ROLE_LABELS, ROLE_PERMISSIONS, Role
from app.core.security import hash_password, verify_password
from app.modules.audit.service import record_audit
from app.modules.customers.models import Reseller
from app.modules.identity.models import PasswordHistory, User
from app.modules.identity.schemas import MeOut, UserCreate, UserUpdate


class AccountLocked(Exception):
    def __init__(self, minutes: int):
        self.minutes = minutes


def authenticate(db: Session, email: str, password: str) -> User | None:
    """The user, or None for a wrong email or password. Raises AccountLocked while the account is locked.

    Wrong passwords in a row are counted; LOGIN_MAX_ATTEMPTS (5) locks the account for LOGIN_LOCK_MINUTES (15).
    The caller commits even when sign-in fails, so the count is kept.
    """
    s = get_settings()
    user = db.execute(select(User).where(func.lower(User.email) == email.strip().lower())).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    now = datetime.now(UTC)
    if user.locked_until and user.locked_until > now:
        raise AccountLocked(max(1, math.ceil((user.locked_until - now).total_seconds() / 60)))
    if not verify_password(password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= s.login_max_attempts:
            user.failed_login_count = 0
            user.locked_until = now + timedelta(minutes=s.login_lock_minutes)
            record_audit(db, actor_id=None, action="user.locked", entity_type="user", entity_id=user.id,
                         summary=f"{user.email} locked for {s.login_lock_minutes} minutes after "
                                 f"{s.login_max_attempts} wrong passwords")
            db.flush()
            raise AccountLocked(s.login_lock_minutes)
        db.flush()
        return None
    user.failed_login_count = 0
    user.locked_until = None
    db.flush()
    return user


def set_password(db: Session, user: User, password: str) -> None:
    """Every password change goes through here: the old hash is kept so recent passwords can't come back."""
    if user.password_hash:
        db.add(PasswordHistory(user_id=user.id, password_hash=user.password_hash))
    user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None


def _recently_used(db: Session, user: User, password: str) -> bool:
    """True when password is the current one or one of the ones before it (PASSWORD_HISTORY in all)."""
    if verify_password(password, user.password_hash):
        return True
    keep = max(0, get_settings().password_history - 1)
    earlier = db.execute(select(PasswordHistory.password_hash).where(PasswordHistory.user_id == user.id)
                         .order_by(PasswordHistory.id.desc()).limit(keep)).scalars() if keep else []
    return any(verify_password(password, h) for h in earlier)


def unlock(db: Session, actor: User, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    _guard_admin_accounts(actor, user.role)
    user.failed_login_count = 0
    user.locked_until = None
    db.flush()
    record_audit(db, actor_id=actor.id, action="user.unlock", entity_type="user", entity_id=user.id,
                 summary=f"Unlocked {user.email}")
    return user


def me_out(user: User) -> MeOut:
    perms = sorted(p.value for p in ROLE_PERMISSIONS[Role(user.role)])
    return MeOut(
        id=user.id, email=user.email, full_name=user.full_name, role=user.role, role_label=ROLE_LABELS[Role(user.role)],
        reseller_id=user.reseller_id, is_active=user.is_active, must_change_password=user.must_change_password,
        permissions=perms,
    )


def _validate_role_reseller(db: Session, role: Role, reseller_id: int | None) -> None:
    if role == Role.RESELLER:
        if reseller_id is None:
            raise BusinessRuleError("Dealer users must be linked to a dealer")
        if db.get(Reseller, reseller_id) is None:
            raise NotFoundError("Dealer not found")
    elif reseller_id is not None:
        raise BusinessRuleError("Only dealer users can be linked to a dealer")


def list_users(db: Session) -> list[User]:
    return list(db.execute(select(User).order_by(User.full_name)).scalars())


def _guard_admin_accounts(actor: User, *roles: Role | str | None) -> None:
    """Only an Administrator may create, promote to, or change an Administrator account (no privilege escalation)."""
    if Role(actor.role) != Role.ADMINISTRATOR and any(r is not None and Role(r) == Role.ADMINISTRATOR for r in roles):
        raise PermissionDeniedError("Only an Administrator can manage Administrator accounts")


def create_user(db: Session, actor: User, data: UserCreate) -> User:
    _guard_admin_accounts(actor, data.role)
    _validate_role_reseller(db, data.role, data.reseller_id)
    user = User(
        email=data.email.lower(), full_name=data.full_name, password_hash=hash_password(data.password),
        role=data.role, reseller_id=data.reseller_id, is_active=True, must_change_password=True,
        phone=(data.phone or "").strip() or None,
    )
    flush_or_conflict(db, user, "A user with this email already exists")
    record_audit(db, actor_id=actor.id, action="user.create", entity_type="user", entity_id=user.id,
                 summary=f"Created user {user.email} with role {user.role}")
    if data.replaces is not None:
        # Same request, same transaction: the new person takes over (or shares) the other person's work.
        from app.modules.identity import handover

        other = db.get(User, data.replaces.user_id)
        take_over = data.replaces.mode == "TAKE_OVER"
        handover.handover(db, actor, data.replaces.user_id, to_user_id=user.id,
                          reseller_ids=None if take_over else (data.replaces.reseller_ids or []),
                          deactivate=take_over,
                          reason=f"{user.full_name} {'replaces' if take_over else 'shares the work of'} "
                                 f"{other.full_name if other else 'a colleague'}")
    return user


def update_user(db: Session, actor: User, user_id: int, data: UserUpdate) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    changes = data.model_dump(exclude_unset=True)
    _guard_admin_accounts(actor, user.role, changes.get("role"))
    role = changes.get("role", user.role)
    reseller_id = changes.get("reseller_id", user.reseller_id)
    if role != Role.RESELLER and "role" in changes and "reseller_id" not in changes:
        reseller_id = None
    _validate_role_reseller(db, Role(role), reseller_id)
    if user.id == actor.id and (changes.get("is_active") is False or ("role" in changes and role != user.role)):
        raise BusinessRuleError("You cannot deactivate yourself or change your own role")
    if changes.get("is_active") is False and user.is_active:
        from app.modules.identity import handover  # nobody's dealers or hand-overs are left without a person (D9)

        handover.ensure_nothing_left(db, user)
    password = changes.pop("password", None)
    for k, v in changes.items():
        setattr(user, k, v)
    user.reseller_id = reseller_id
    if password:
        set_password(db, user, password)          # also clears a lock: a reset password lets them sign in again
        user.must_change_password = user.id != actor.id
    db.flush()
    record_audit(db, actor_id=actor.id, action="user.update", entity_type="user", entity_id=user.id,
                 summary=f"Updated user {user.email}",
                 details={k: str(v) for k, v in changes.items()} | ({"password": "changed"} if password else {}))
    return user


def change_own_password(db: Session, user: User, current_password: str, new_password: str) -> User:
    if not verify_password(current_password, user.password_hash):
        raise BusinessRuleError("Current password is incorrect")
    if _recently_used(db, user, new_password):
        n = get_settings().password_history
        raise BusinessRuleError(f"Choose a password you haven't used recently (not the current one or the {n - 1} before it)")
    set_password(db, user, new_password)
    user.must_change_password = False
    db.flush()
    record_audit(db, actor_id=user.id, action="user.password_change", entity_type="user", entity_id=user.id,
                 summary=f"{user.email} changed their password")
    return user
