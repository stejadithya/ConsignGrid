"""Approval details shared by stock requests and replenishment requests (findings 17 and 22).

Kept apart from the schemas modules so both can use it without importing each other.
"""

from pydantic import BaseModel, Field, model_validator

from app.modules.stock_requests.models import ApprovalMethod


class ApprovalIn(BaseModel):
    """Who approved is the signed-in user; this records how, with whom, and why (finding 17)."""

    method: ApprovalMethod
    contact: str | None = Field(default=None, max_length=200)   # who they spoke to; not needed for a standard approval
    comments: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def _contact_needed(self) -> "ApprovalIn":
        self.comments = self.comments.strip()
        self.contact = (self.contact or "").strip() or None
        if len(self.comments) < 3:
            raise ValueError("Comments must be at least 3 characters")
        if self.method != ApprovalMethod.STANDARD and not self.contact:
            raise ValueError("Say who you spoke to (not needed for a standard approval)")
        return self
