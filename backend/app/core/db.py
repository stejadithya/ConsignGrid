from collections.abc import Iterator
from datetime import datetime

from sqlalchemy import DateTime, MetaData, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        s = get_settings()
        kwargs: dict = {"pool_pre_ping": True, "future": True}
        if s.db_disable_pool:
            from sqlalchemy.pool import NullPool

            kwargs = {"poolclass": NullPool, "future": True}
        if s.db_disable_prepared_statements:
            kwargs["connect_args"] = {"prepare_threshold": None}
        _engine = create_engine(s.database_url, **kwargs)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=True, expire_on_commit=False)
    return _engine


def session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """Request-scoped session. Routers commit explicitly; anything uncommitted is rolled back."""
    db = session_factory()()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def flush_or_conflict(db: Session, obj: object | None, message: str) -> None:
    """Flush pending changes inside a savepoint, translating unique violations into ConflictError."""
    from sqlalchemy.exc import IntegrityError

    from app.core.errors import ConflictError

    try:
        with db.begin_nested():
            if obj is not None:
                db.add(obj)
            db.flush()
    except IntegrityError as exc:
        raise ConflictError(message) from exc
