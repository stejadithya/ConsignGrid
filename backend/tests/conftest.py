"""Test fixtures. Tests run against a real PostgreSQL database (locking and constraints matter).

Set TEST_DATABASE_URL to override the default local test database.
"""

import os

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://tyreworld:tyreworld@localhost:5432/tyreworld_test"
)


def is_disposable_test_url(url: str) -> bool:
    """The suite DROPS the whole schema, so it only runs against a local database whose name ends in _test."""
    from sqlalchemy.engine import make_url

    u = make_url(url)
    return (u.host in ("localhost", "127.0.0.1", "::1", None)) and (u.database or "").endswith("_test")


if not is_disposable_test_url(TEST_DB_URL):
    raise SystemExit(f"Refusing to run tests against {TEST_DB_URL.split('@')[-1]}: the test suite wipes its database. "
                     "Use a local database whose name ends in _test.")
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["APP_ENV"] = "test"

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from alembic import command  # noqa: E402
from app.core.db import Base, session_factory  # noqa: E402

HERE = os.path.dirname(__file__)
BACKEND = os.path.dirname(HERE)


@pytest.fixture(scope="session", autouse=True)
def _migrated_database():
    engine = create_engine(TEST_DB_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    engine.dispose()
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _clean_tables(_migrated_database):
    """Truncate everything and restore the system locations before each test."""
    import app.models  # noqa: F401
    from app.modules.customers.models import SYSTEM_LOCATIONS

    engine = create_engine(TEST_DB_URL)
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        for loc_type, code, name in SYSTEM_LOCATIONS:
            conn.execute(
                text("INSERT INTO locations (code, name, type, is_default_warehouse, is_active) "
                     "VALUES (:c, :n, :t, false, true)"),
                {"c": code, "n": name, "t": loc_type.value},
            )
    engine.dispose()
    yield


@pytest.fixture
def db():
    session = session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


from tests.factories import *  # noqa: E402,F401,F403
