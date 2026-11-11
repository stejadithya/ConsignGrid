"""Database diagnostics: actionable, and never leak credentials."""

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.dbcheck import redact, run_check


def test_health_db_reports_connected_and_migrated(client):
    r = client.get("/api/health/db")
    body = r.json()
    assert body["connected"] is True and body["migration_version"]
    assert body["status"] == "warning" and body["code"] == "no_users"   # clean test DB has no users


def test_health_db_ok_with_users(world):
    body = world.client.get("/api/health/db").json()
    assert body["status"] == "ok" and body["users"] >= 1


def test_unreachable_default_database_explains_missing_env_var():
    s = Settings(database_url="postgresql://u:topsecret@localhost:1/db")
    report = run_check(create_engine(s.database_url, poolclass=NullPool), s)
    assert report["status"] == "error" and report["code"] == "database_unreachable"
    assert "DATABASE_URL is not set" in report["hint"]
    assert "topsecret" not in str(report)


def test_unreachable_remote_database_hint():
    s = Settings(database_url="postgresql://u:topsecret@db.invalid:5432/neondb?sslmode=require&connect_timeout=2")
    report = run_check(create_engine(s.database_url, poolclass=NullPool), s)
    assert report["code"] == "database_unreachable" and "Check DATABASE_URL" in report["hint"]
    assert report["target"]["host"] == "db.invalid" and "topsecret" not in str(report)


def test_redact_hides_credentials():
    msg = 'failed for postgresql+psycopg://neondb_owner:npg_secret@ep-x.neon.tech/db password=npg_secret'
    out = redact(msg)
    assert "npg_secret" not in out and "ep-x.neon.tech" in out
