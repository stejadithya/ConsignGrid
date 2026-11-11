"""Human-readable, gap-tolerant document numbers (e.g. SAL-000042) from a locked counter row."""

from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base


class NumberSequence(Base):
    __tablename__ = "number_sequences"

    prefix: Mapped[str] = mapped_column(String(10), primary_key=True)
    next_value: Mapped[int] = mapped_column(nullable=False, default=1)


def next_number(db: Session, prefix: str) -> str:
    db.execute(
        text("INSERT INTO number_sequences (prefix, next_value) VALUES (:p, 1) ON CONFLICT (prefix) DO NOTHING"),
        {"p": prefix},
    )
    value = db.execute(
        text(
            "UPDATE number_sequences SET next_value = next_value + 1 WHERE prefix = :p RETURNING next_value - 1"
        ),
        {"p": prefix},
    ).scalar_one()
    return f"{prefix}-{value:06d}"
