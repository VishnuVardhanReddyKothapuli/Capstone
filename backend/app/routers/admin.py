"""Administrator-only operational summary. Never returns another user's records."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.deps import AdminUser, DbSession
from app.models import Check, User

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/summary")
def summary(_: AdminUser, db: DbSession) -> dict[str, int]:
    """Small aggregate only; access control is enforced by the dependency."""
    return {
        "users": int(db.execute(select(func.count()).select_from(User)).scalar_one()),
        "checks": int(db.execute(select(func.count()).select_from(Check)).scalar_one()),
    }
