from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

PASSWORD_MIN = 10
PASSWORD_MAX_BYTES = 72   # bcrypt reads at most 72 bytes; longer passwords are refused rather than silently cut


def password_problem(password: str) -> str | None:
    """Why this password can't be used, in plain words (None = fine). Any characters are allowed."""
    if len(password) < PASSWORD_MIN:
        return f"Use at least {PASSWORD_MIN} characters"
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        return "Use 72 characters or fewer (fewer if the password has accented letters or emoji)"
    return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=s.access_token_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
