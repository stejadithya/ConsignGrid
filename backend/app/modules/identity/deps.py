"""Authentication and authorisation dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import DomainError, PermissionDeniedError
from app.core.permissions import P, role_has
from app.core.security import decode_access_token
from app.modules.identity.models import User


class NotAuthenticatedError(DomainError):
    status_code = 401
    code = "not_authenticated"


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(get_settings().auth_cookie_name)


def get_current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    token = _extract_token(request)
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        raise NotAuthenticatedError("Not authenticated")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise NotAuthenticatedError("Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DB = Annotated[Session, Depends(get_db)]


def require(*permissions: P):
    """Dependency factory: the current user must hold every listed permission."""

    def checker(user: CurrentUser) -> User:
        for perm in permissions:
            if not role_has(user.role, perm):
                raise PermissionDeniedError(f"Missing permission: {perm.value}")
        return user

    return checker


def has(user: User, permission: P) -> bool:
    return role_has(user.role, permission)
