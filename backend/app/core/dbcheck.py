"""Database diagnostics that are safe to show: never include passwords or full connection strings."""

import re

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, OperationalError

from app.core.config import Settings

LOCAL_DEFAULT_HOSTS = {"localhost", "127.0.0.1"}

_CREDENTIALS = re.compile(r"(postgres(?:ql)?(?:\+\w+)?://)[^@\s/]+@", re.IGNORECASE)
_PASSWORD_KV = re.compile(r"password=\S+", re.IGNORECASE)


def redact(message: str) -> str:
    return _PASSWORD_KV.sub("password=***", _CREDENTIALS.sub(r"\1***@", message)).strip()


def target(settings: Settings) -> dict:
    """Where the API is configured to connect (host and database name only)."""
    try:
        url = make_url(settings.database_url)
    except Exception:  # noqa: BLE001
        return {"host": None, "database": None, "valid_url": False}
    host = url.host or ""
    return {
        "host": host,
        "database": url.database,
        "valid_url": True,
        "pooled": "-pooler" in host,
        "looks_like_local_default": host in LOCAL_DEFAULT_HOSTS,
    }


def explain(exc: Exception, settings: Settings) -> dict:
    """Turn a database exception into a code and a human hint."""
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    info = target(settings)
    if isinstance(exc, OperationalError) and sqlstate is None:
        if info.get("looks_like_local_default"):
            hint = ("DATABASE_URL is not set for this deployment, so the API is trying a local database. "
                    "Add DATABASE_URL (the pooled Neon URL) for the Production environment and redeploy.")
        else:
            hint = ("Could not connect to the database. Check DATABASE_URL (host, password, ?sslmode=require) "
                    "and that the Neon database is not deleted or suspended, then redeploy.")
        code = "database_unreachable"
    elif sqlstate == "42P01":
        code, hint = "database_not_initialised", (
            "A table this version of the app needs is missing: the database has not been migrated to the latest "
            "version (or is empty). Run GitHub Actions → Database setup with no boxes ticked; it applies pending "
            "migrations and keeps all data. It must target the SAME database the API uses "
            "(DATABASE_URL_UNPOOLED must belong to the same Neon database as DATABASE_URL).")
    elif sqlstate in ("28P01", "28000"):
        code, hint = "database_auth_failed", "The database rejected the username/password in DATABASE_URL."
    elif sqlstate == "26000" or "prepared statement" in str(exc).lower():
        code, hint = "prepared_statements", "Set DB_DISABLE_PREPARED_STATEMENTS=true and redeploy."
    else:
        code, hint = "database_error", "Unexpected database error; see the runtime logs for details."
    return {"code": code, "hint": hint, "sqlstate": sqlstate, "error": redact(str(getattr(exc, "orig", exc)))[:500],
            "database_host": info.get("host"), "database_name": info.get("database")}


def run_check(engine, settings: Settings) -> dict:
    """Connect, check migrations and user data. Returns a report with status ok|warning|error."""
    report: dict = {"target": target(settings)}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            report["connected"] = True
            has_versions = conn.execute(text("SELECT to_regclass('public.alembic_version') IS NOT NULL")).scalar()
            report["migration_version"] = (
                conn.execute(text("SELECT version_num FROM alembic_version")).scalar() if has_versions else None
            )
            if report["migration_version"] is None:
                report.update(status="error", code="database_not_initialised",
                              hint="Run GitHub Actions → Database setup (migrations) against this database.")
                return report
            report["users"] = conn.execute(text("SELECT count(*) FROM users")).scalar()
            report["resellers"] = conn.execute(text("SELECT count(*) FROM resellers")).scalar()
    except (OperationalError, DBAPIError) as exc:
        report.update(status="error", connected=report.get("connected", False), **explain(exc, settings))
        return report
    if not report["users"]:
        report.update(status="warning", code="no_users",
                      hint="Tables exist but there are no users. Create the pilot accounts "
                           "(GitHub Actions → Database setup → Reset to clean pilot state).")
    else:
        report["status"] = "ok"
    return report
