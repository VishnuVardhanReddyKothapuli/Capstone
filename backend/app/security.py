"""Password hashing (bcrypt) and JWT access tokens."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.config import settings


def _prehash(password: str) -> bytes:
    """SHA-256 -> base64 before bcrypt.

    bcrypt silently ignores everything past the 72nd byte of its input. Hashing
    first means a long passphrase stays fully significant, and the 44-byte
    base64 digest always fits.
    """
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed stored hash — treat as a failed login, never a 500.
        return False


def create_access_token(*, user_id: int, username: str) -> tuple[str, int]:
    """Returns `(token, expires_in_seconds)`."""
    expires_in = settings.JWT_EXPIRE_MINUTES * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": secrets.token_urlsafe(16),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, expires_in


class TokenError(Exception):
    """Token missing, malformed, expired, or signed with the wrong key."""


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER, audience=settings.JWT_AUDIENCE,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
