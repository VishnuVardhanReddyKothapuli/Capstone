"""POST /api/checks/{id}/explain — Gemini's written second opinion on a check.

Kept out of `/api/moderate` on purpose. The explanation is an outbound call to a
third party carrying the user's image, it costs money per request, and it is
slower than both local models put together — so it happens only when the owner of
the image asks for it, and the answer is cached on the row afterwards.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import Check, utcnow
from app.schemas import CheckResult, check_to_result
from app.services import explainer, images

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["moderation"])


@router.post("/checks/{check_id}/explain", response_model=CheckResult)
def explain_check(
    check_id: int,
    current_user: CurrentUser,
    db: DbSession,
    refresh: Annotated[bool, Query(description="Ignore a cached answer and ask again.")] = False,
) -> CheckResult:
    """Explain why a stored check is safe or unsafe, and cache the answer.

    Owner-only, for the same reason `GET /api/checks/{id}/image` is: this sends
    the image itself to an external service, so only the account that uploaded it
    may trigger that.
    """
    check = db.execute(select(Check).where(Check.id == check_id)).scalar_one_or_none()
    if check is None or check.user_id != current_user.id:
        # Same 404 either way: whether check #5 exists is not another account's
        # business.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such check.")

    if check.explanation_json and not refresh:
        return check_to_result(check)

    try:
        decoded = images.decode(bytes(check.image_blob))
    except images.UnsupportedImageError as exc:
        # Stored bytes that no longer decode: not the caller's fault, and not
        # something a retry will fix.
        logger.error("Stored image for check %s is undecodable: %s", check_id, exc)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "The stored image could not be decoded."
        ) from exc

    try:
        result = explainer.explain(
            decoded.frames[0], frame_index=0, frames_total=decoded.frame_count
        )
    except explainer.ExplainerNotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except explainer.ExplainerRateLimited as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    except explainer.ExplainerTimeout as exc:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, str(exc)) from exc
    except explainer.ExplainerBlocked as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except explainer.ExplainerError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    check.explanation_json = json.dumps(result.to_dict(), separators=(",", ":"))
    check.explained_at = utcnow()
    db.add(check)
    db.commit()
    return check_to_result(check)
