"""Create (or repair) the TyreGrow Administrator — a super user with every permission. Safe on a live database:
it never deletes or changes any business data.

    PILOT_ADMIN_EMAIL=… PILOT_ADMIN_PASSWORD=… python -m scripts.create_admin [--reset-password]

  PILOT_ADMIN_EMAIL     required — the administrator's login email
  PILOT_ADMIN_NAME      optional — display name (default "Administrator")
  PILOT_ADMIN_PASSWORD  default password (at least 10 characters). Required in GitHub Actions; generated and
                        printed once elsewhere if absent. It must be changed at first sign-in.

If the email already exists it is made an active Administrator; its password is only replaced with
--reset-password (then it must be changed at the next sign-in).
"""

import argparse
import os
import secrets
import sys

from sqlalchemy import func, select

import app.models  # noqa: F401
from app.core.db import session_factory
from app.core.permissions import Role
from app.core.security import hash_password
from app.modules.audit.service import record_audit
from app.modules.identity.models import User


def create_admin(reset_password: bool = False) -> User:
    email = (os.environ.get("PILOT_ADMIN_EMAIL") or "").strip().lower()
    if not email:
        sys.exit("Missing PILOT_ADMIN_EMAIL (the administrator's login email).")
    name = (os.environ.get("PILOT_ADMIN_NAME") or "").strip() or "Administrator"
    password = (os.environ.get("PILOT_ADMIN_PASSWORD") or "").strip()
    if password and len(password) < 10:
        sys.exit("PILOT_ADMIN_PASSWORD must be at least 10 characters.")
    if not password and os.environ.get("GITHUB_ACTIONS") == "true":
        sys.exit("Add the PILOT_ADMIN_PASSWORD repository secret (default password, at least 10 characters).")
    generated = not password
    password = password or secrets.token_urlsafe(12)

    db = session_factory()()
    try:
        user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
        if user is None:
            user = User(email=email, full_name=name, password_hash=hash_password(password), role=Role.ADMINISTRATOR,
                        is_active=True, must_change_password=True)
            db.add(user)
            db.flush()
            action, set_pw = "created", True
        else:
            user.role, user.reseller_id, user.is_active, user.full_name = Role.ADMINISTRATOR, None, True, name
            set_pw = reset_password
            if set_pw:
                user.password_hash, user.must_change_password = hash_password(password), True
            db.flush()
            action = "updated (password reset)" if set_pw else "updated (password unchanged)"
        record_audit(db, actor_id=None, action="user.admin_setup", entity_type="user", entity_id=user.id,
                     summary=f"Administrator {email} {action} by set-up script")
        db.commit()
        print(f"Administrator {email} {action}.")
        if set_pw:
            shown = password if generated else "(from PILOT_ADMIN_PASSWORD)"
            print(f"Default password: {shown} — it must be changed at first sign-in.")
        return user
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or repair the TyreGrow Administrator account.")
    parser.add_argument("--reset-password", action="store_true", help="replace the password of an existing account")
    create_admin(parser.parse_args().reset_password)


if __name__ == "__main__":
    main()
