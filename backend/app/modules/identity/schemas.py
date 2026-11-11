from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.permissions import Role
from app.core.security import password_problem


def _checked(password: str | None) -> str | None:
    """Every password a person sets: at least 10 characters, at most 72 bytes; any characters allowed."""
    problem = password_problem(password) if password else None
    if problem:
        raise ValueError(problem)
    return password


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: Role
    reseller_id: int | None
    is_active: bool
    phone: str | None = None
    locked_until: datetime | None = None    # set while the account is locked after too many wrong passwords


class MeOut(UserOut):
    role_label: str
    must_change_password: bool
    permissions: list[str]


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)

    @field_validator("new_password")
    @classmethod
    def _new_ok(cls, v: str) -> str:
        return _checked(v)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: MeOut


class ReplacesIn(BaseModel):
    """New user form: "Is this person replacing someone?" (finding 32)."""

    user_id: int
    mode: Literal["TAKE_OVER", "SHARE"]   # TAKE_OVER: everything, and the other person is deactivated
    reseller_ids: list[int] | None = None  # SHARE: the dealers to share


class HandoverIn(BaseModel):
    to_user_id: int
    reseller_ids: list[int] | None = None   # None = everything
    deactivate: bool = False
    reason: str = Field(min_length=3, max_length=500)


class HandoverOut(BaseModel):
    dealers: int
    deliveries: int
    transfers: int
    approvals: int
    summary: str
    deactivated: bool


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=10, max_length=200)
    role: Role
    reseller_id: int | None = None
    phone: str | None = Field(default=None, max_length=50)
    replaces: ReplacesIn | None = None

    @field_validator("password")
    @classmethod
    def _password_ok(cls, v: str) -> str:
        return _checked(v)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    role: Role | None = None
    reseller_id: int | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=200)

    @field_validator("password")
    @classmethod
    def _password_ok(cls, v: str | None) -> str | None:
        return _checked(v)
