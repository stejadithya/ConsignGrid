from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class FeedbackType(StrEnum):
    ISSUE = "ISSUE"
    IMPROVEMENT = "IMPROVEMENT"
    QUESTION = "QUESTION"
    OTHER = "OTHER"


class PilotFeedback(TimestampMixin, Base):
    """Feedback captured from business users during the pilot. The role is stored as submitted."""

    __tablename__ = "pilot_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    page: Mapped[str] = mapped_column(String(200), nullable=False)
    feedback_type: Mapped[FeedbackType] = mapped_column(
        Enum(FeedbackType, name="feedback_type", native_enum=False, length=20), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
