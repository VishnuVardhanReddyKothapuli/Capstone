"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models import User
from app.security import TokenError, decode_token

# auto_error=False so this module owns the 401 shape and the WWW-Authenticate header.
bearer_scheme = HTTPBearer(auto_error=False, description="JWT from POST /api/auth/login")

DbSession = Annotated[Session, Depends(get_db)]
BearerCreds = Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)]

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(credentials: BearerCreds, db: DbSession) -> User:
    if credentials is None or not credentials.credentials:
        raise UNAUTHORIZED
    try:
        payload = decode_token(credentials.credentials)
    except TokenError:
        raise UNAUTHORIZED from None

    subject = payload.get("sub")
    if subject is None:
        raise UNAUTHORIZED
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise UNAUTHORIZED from None

    user = db.get(User, user_id)
    if user is None:
        # Valid signature but the account is gone.
        raise UNAUTHORIZED
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_admin_user(current_user: CurrentUser) -> User:
    """Authorization is evaluated on the server for every admin request."""
    if not settings.admin_email or (current_user.email or "").casefold() != settings.admin_email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
    return current_user


AdminUser = Annotated[User, Depends(get_admin_user)]
