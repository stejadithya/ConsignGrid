"""Data scoping for reseller users. Out-of-scope records are reported as not found (no information leak)."""

from app.core.errors import NotFoundError
from app.modules.identity.models import User


def scoped_reseller_id(user: User) -> int | None:
    """The reseller a user is restricted to, or None for dealership staff."""
    return user.reseller_id if user.is_reseller_user else None


def ensure_reseller_access(user: User, reseller_id: int | None, what: str = "Record") -> None:
    restricted = scoped_reseller_id(user)
    if restricted is not None and reseller_id != restricted:
        raise NotFoundError(f"{what} not found")
