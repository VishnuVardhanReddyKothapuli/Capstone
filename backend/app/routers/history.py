"""GET /api/history — the signed-in user's past checks, newest first."""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.deps import CurrentUser, DbSession
from app.models import Check
from app.schemas import CheckResult, HistoryPage, check_to_result

router = APIRouter(prefix="/api", tags=["history"])

CheckTypeFilter = Optional[Literal["nsfw", "similarity", "both"]]


@router.get("/history", response_model=HistoryPage)
def list_history(
    current_user: CurrentUser,
    db: DbSession,
    check_type: Annotated[CheckTypeFilter, Query(description="Filter by check type.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> HistoryPage:
    """Paginated history for the current account.

    History is per-user; the similarity *search* is global. Rows carry thumbnail
    URLs rather than blob bytes.
    """
    filters = [Check.user_id == current_user.id]
    if check_type is not None:
        filters.append(Check.check_type == check_type)

    total = db.execute(select(func.count()).select_from(Check).where(*filters)).scalar_one()

    rows = (
        db.execute(
            select(Check)
            # Eager-load the matched row: check_to_result reads it, and without
            # this the page would fire one extra SELECT per result.
            .options(selectinload(Check.similarity_match))
            .where(*filters)
            .order_by(Check.created_at.desc(), Check.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return HistoryPage(
        items=[check_to_result(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/checks/{check_id}", response_model=CheckResult)
def get_check(check_id: int, current_user: CurrentUser, db: DbSession) -> CheckResult:
    """A single check's full verdict, owner-scoped."""
    check = db.get(Check, check_id)
    if check is None or check.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such check.")
    return check_to_result(check)
