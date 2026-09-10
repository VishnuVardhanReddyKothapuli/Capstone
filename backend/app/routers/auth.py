"""Registration, login, and the current-user probe."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.deps import CurrentUser, DbSession
from app.models import User
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)

# Compared against when the username does not exist, so a wrong username and a
# wrong password take about the same time and cannot be told apart by timing.
_DUMMY_HASH = hash_password("timing-equaliser")


def _issue(user: User) -> TokenResponse:
    token, expires_in = create_access_token(user_id=user.id, username=user.username)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserOut(
            id=user.id, username=user.username, created_at=user.created_at,
            is_admin=bool(settings.admin_email and (user.email or "").casefold() == settings.admin_email),
        ),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DbSession) -> TokenResponse:
    username = payload.username.strip()
    existing = db.execute(
        select(User).where(func.lower(User.username) == username.lower())
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That username or email is already in use."
        )
    if payload.email:
        existing_email = db.execute(
            select(User).where(func.lower(User.email) == payload.email.strip().lower())
        ).scalars().first()
        if existing_email is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="That username or email is already in use."
            )

    user = User(username=username, email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("Registration conflict for username=%r", username)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That username or email is already in use."
        ) from None
    db.refresh(user)
    return _issue(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    candidates = db.execute(
        select(User).where(func.lower(User.username) == payload.username.lower())
    ).scalars().all()

    user: User | None = None
    for candidate in candidates:
        if verify_password(payload.password, candidate.password_hash):
            user = candidate
            break

    if user is None:
        verify_password(payload.password, _DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password."
        )
    return _issue(user)


@router.get("/me", response_model=UserOut)
def me(current_user: CurrentUser) -> UserOut:
    return UserOut(
        id=current_user.id, username=current_user.username, created_at=current_user.created_at,
        is_admin=bool(settings.admin_email and (current_user.email or "").casefold() == settings.admin_email),
    )
