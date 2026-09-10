"""Similarity check: Chroma nearest-neighbour lookup + SQL match resolution.

Note on scope: the vector search is intentionally **global**, not per-user. The
whole point of the check is to notice that an image already exists in the corpus,
including when a different account uploaded it first — that is what powers the
"Original uploader" field on the result card. History, by contrast, is per-user.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Check
from app.services import tiers, vector_store


@dataclass(frozen=True)
class SimilarityResult:
    """The five values the similarity result card shows, plus the tier severity."""

    top_score: float | None
    tier: str
    match_count: int
    match_check_id: int | None
    match_created_at: datetime | None
    match_filename: str | None

    @property
    def severity(self) -> str:
        return tiers.severity_of_similarity_tier(self.tier)


def analyse(embedding: list[float], db: Session, user_id: int) -> SimilarityResult:
    """Query the vector store and resolve the best match back to its SQL row.

    The vector search is intentionally **global**: a duplicate is found even when
    a different account uploaded the original.  History (per-user) is enforced
    elsewhere.  Must run before the current upload's vector is added to Chroma,
    or the image matches itself at 1.0.
    """
    scan_k = max(settings.SIMILARITY_TOP_K, settings.SIMILARITY_COUNT_K)
    # Global search — no user_id filter on the Chroma query.
    neighbours = vector_store.query(embedding, top_k=scan_k)

    above_floor = [n for n in neighbours if n.score >= settings.SIM_MATCH_FLOOR]
    best = neighbours[0] if neighbours else None
    top_score = best.score if best else None
    tier = tiers.classify_similarity_tier(top_score)

    # Only surface "the original" when the best neighbour actually counts as a
    # match; below the floor the card shows em dashes instead.
    # The match may belong to another user — that is the point of a global
    # corpus.  The full-size original stays owner-protected (get_image checks).
    match: Check | None = None
    if above_floor:
        match = db.execute(
            select(Check).where(Check.id == above_floor[0].check_id)
        ).scalar_one_or_none()

    return SimilarityResult(
        top_score=top_score,
        tier=tier,
        match_count=len(above_floor),
        match_check_id=match.id if match else None,
        match_created_at=match.created_at if match else None,
        match_filename=match.filename if match else None,
    )


def register(check: Check, embedding: list[float]) -> None:
    """Store the new image's vector so later uploads can match against it."""
    vector_store.add(
        check_id=check.id,
        embedding=embedding,
        metadata={
            "user_id": check.user_id,
        },
    )
