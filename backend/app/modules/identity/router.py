from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.core.config import get_settings
from app.core.permissions import P, Role
from app.core.security import create_access_token
from app.modules.identity import handover as handover_service
from app.modules.identity import service
from app.modules.identity.deps import DB, CurrentUser, NotAuthenticatedError, require
from app.modules.identity.models import User
from app.modules.identity.schemas import (
    HandoverIn,
    HandoverOut,
    LoginRequest,
    MeOut,
    PasswordChange,
    TokenOut,
    UserCreate,
    UserOut,
    UserUpdate,
)

router = APIRouter(tags=["identity"])


@router.post("/auth/login", response_model=TokenOut)
def login(data: LoginRequest, response: Response, db: DB):
    try:
        user = service.authenticate(db, data.email, data.password)
    except service.AccountLocked as locked:
        db.commit()   # keep the lock
        raise NotAuthenticatedError(
            f"Too many wrong passwords. This account is locked for {locked.minutes} more minute"
            f"{'' if locked.minutes == 1 else 's'}. Try again later, or ask a Relationship Manager to unlock it.",
            code="account_locked") from None
    db.commit()       # the wrong-password count, or its reset
    if user is None:
        raise NotAuthenticatedError("Invalid email or password")
    token = create_access_token(user.id)
    s = get_settings()
    response.set_cookie(
        s.auth_cookie_name, token, httponly=True, samesite="strict", secure=s.auth_cookie_secure,
        max_age=s.access_token_minutes * 60, path="/",
    )
    return TokenOut(access_token=token, user=service.me_out(user))


@router.post("/auth/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(get_settings().auth_cookie_name, path="/")


@router.get("/auth/me", response_model=MeOut)
def me(user: CurrentUser):
    return service.me_out(user)


@router.post("/auth/password", response_model=MeOut)
def change_password(data: PasswordChange, db: DB, user: CurrentUser):
    """Any signed-in user may change their own password (required after a set-up/temporary password)."""
    service.change_own_password(db, user, data.current_password, data.new_password)
    db.commit()
    return service.me_out(user)


@router.get("/users", response_model=list[UserOut])
def list_users(db: DB, _: Annotated[User, Depends(require(P.USER_MANAGE))]):
    return service.list_users(db)


@router.get("/staff", response_model=list[UserOut])
def list_staff(db: DB, _: Annotated[User, Depends(require(P.RESELLER_READ))], role: Role | None = None):
    """Active dealership staff (e.g. ?role=SALES_REP for assigning sales representatives)."""
    return [u for u in service.list_users(db) if u.is_active and not u.is_reseller_user and (role is None or u.role == role)]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(data: UserCreate, db: DB, actor: Annotated[User, Depends(require(P.USER_MANAGE))]):
    user = service.create_user(db, actor, data)
    db.commit()
    return user


@router.post("/users/{user_id}/handover", response_model=HandoverOut)
def handover(user_id: int, data: HandoverIn, db: DB, actor: Annotated[User, Depends(require(P.USER_MANAGE))]):
    """Hand a person's dealers, carried deliveries/transfers and waiting approvals to a colleague with the same role."""
    moved = handover_service.handover(db, actor, user_id, to_user_id=data.to_user_id, reseller_ids=data.reseller_ids,
                                      deactivate=data.deactivate, reason=data.reason)
    db.commit()
    return HandoverOut(dealers=len(moved.dealers), deliveries=len(moved.deliveries), transfers=len(moved.transfers),
                       approvals=len(moved.stock_requests) + len(moved.replenishments), summary=moved.summary(),
                       deactivated=data.deactivate)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db: DB, actor: Annotated[User, Depends(require(P.USER_MANAGE))]):
    user = service.update_user(db, actor, user_id, data)
    db.commit()
    return user


@router.post("/users/{user_id}/unlock", response_model=UserOut)
def unlock_user(user_id: int, db: DB, actor: Annotated[User, Depends(require(P.USER_MANAGE))]):
    """Let a person sign in again straight away after too many wrong passwords."""
    user = service.unlock(db, actor, user_id)
    db.commit()
    return user
