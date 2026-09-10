"""Pydantic request/response models and ORM -> response serialisation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, Field, ValidationError, field_validator

from app.models import Check
from app.services import tiers

logger = logging.getLogger(__name__)

CheckType = Literal["nsfw", "similarity", "both"]
Tier = Literal["safe", "suggestive", "explicit"]
Color = Literal["green", "amber", "red"]
# The explainer has its own five-way vocabulary, deliberately wider than `Tier`:
# it can call out violence or hate, which a two-class NSFW model cannot see.
ExplainClass = Literal["safe", "suggestive", "nsfw", "violent", "hate"]


def _as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; stamp them UTC so JSON carries a zone."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


UtcDateTime = Annotated[datetime, AfterValidator(_as_utc)]


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    password: str = Field(min_length=8, max_length=256)
    email: Optional[str] = Field(default=None, max_length=254)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip().casefold()
        if "@" not in cleaned or cleaned.count("@") != 1:
            raise ValueError("Enter a valid email address.")
        local, domain = cleaned.rsplit("@", 1)
        if not local or "." not in domain:
            raise ValueError("Enter a valid email address.")
        return cleaned


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: int
    username: str
    created_at: UtcDateTime
    is_admin: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut


# --------------------------------------------------------------------------- #
# Check results
# --------------------------------------------------------------------------- #
class NsfwBlock(BaseModel):
    """Five values, all traceable to Falconsai's two-class output."""

    nsfw_score: float = Field(description="Model's `nsfw` probability, 0-1.")
    safe_score: float = Field(description="Model's `normal` probability, 0-1.")
    tier: Tier
    threshold: float = Field(description="Explicit threshold in force at check time.")
    frames_analyzed: int
    frame_count: int
    color: Color


class SimilarityMatch(BaseModel):
    check_id: int
    filename: str
    created_at: UtcDateTime
    thumbnail_url: str
    uploaded_by: str = "anonymous"


class SimilarityBlock(BaseModel):
    """Five values: score, band, original uploader, original date, match count."""

    top_score: Optional[float] = None
    tier: str
    match_count: int
    match: Optional[SimilarityMatch] = None
    color: Color


class ExplanationBlock(BaseModel):
    """Gemini's written second opinion, normalised by `services.explainer`.

    A cross-check rather than an input: it never moves `overall_tier`, so the
    card can show the two verdicts side by side and disagree visibly.
    """

    classification: ExplainClass
    confidence: float = Field(description="The score of the chosen class, 0-1.")
    scores: dict[str, float] = Field(description="One score per class, totalling 1.")
    detected_text: Optional[str] = Field(default=None, description="Text read in the image.")
    text_toxicity: float
    description: str = Field(description="Neutral description of what is visible.")
    explanation: str = Field(description="Why this classification, and publish or block.")
    publish_allowed: bool = Field(description="True only for `safe` (rule 7).")
    model: str
    frame_index: int = Field(description="Which sampled frame was sent.")
    frames_total: int = Field(description="Frames in the source file.")
    repaired: bool = Field(description="The model's own scores were inconsistent and were fixed.")


class CheckResult(BaseModel):
    """One row of `checks`, fully rendered. Used by /api/moderate and /api/history."""

    check_id: int
    check_type: CheckType
    filename: str
    content_type: str
    created_at: UtcDateTime
    overall_tier: Tier
    overall_color: Color
    image_url: str
    thumbnail_url: str
    uploaded_by: str = "anonymous"
    nsfw: Optional[NsfwBlock] = None
    similarity: Optional[SimilarityBlock] = None
    explanation: Optional[ExplanationBlock] = None
    explained_at: Optional[UtcDateTime] = None


class HistoryPage(BaseModel):
    items: list[CheckResult]
    total: int
    limit: int
    offset: int


class ModelInfo(BaseModel):
    """Powers the "Models & Tech Stack" view — real config, not hardcoded copy."""

    nsfw_model: str
    nsfw_labels: list[str]
    nsfw_explicit_threshold: float
    nsfw_suggestive_threshold: float
    nsfw_model_loaded: bool
    embedding_model: str
    embedding_dim: int
    embedding_model_loaded: bool
    vector_store: str
    vector_store_collection: str
    vector_store_count: int
    relational_store: str
    backend: str
    max_gif_frames: int
    max_upload_bytes: int
    similarity_bands: dict[str, float]
    explainer_model: str
    explainer_configured: bool
    app_version: str
    environment: str
    deployment: str


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #
def _explanation_of(check: Check) -> ExplanationBlock | None:
    """Parse the stored explanation, tolerating a row written by an older shape."""
    if not check.explanation_json:
        return None
    try:
        return ExplanationBlock.model_validate_json(check.explanation_json)
    except ValidationError:
        logger.warning("Ignoring unreadable explanation on check %s", check.id)
        return None


def check_to_result(check: Check) -> CheckResult:
    """Build the API response for a stored check. Never inlines blob bytes."""
    nsfw: NsfwBlock | None = None
    if check.nsfw_tier is not None and check.nsfw_score is not None:
        nsfw = NsfwBlock(
            nsfw_score=check.nsfw_score,
            safe_score=check.safe_score if check.safe_score is not None else 1.0 - check.nsfw_score,
            tier=check.nsfw_tier,
            threshold=check.nsfw_threshold or 0.0,
            frames_analyzed=check.frames_analyzed or 1,
            frame_count=check.frame_count or 1,
            color=tiers.color_of(check.nsfw_tier),
        )

    similarity: SimilarityBlock | None = None
    if check.similarity_tier is not None:
        match: SimilarityMatch | None = None
        matched = check.similarity_match
        if matched is not None:
            match = SimilarityMatch(
                check_id=matched.id,
                filename=matched.filename,
                created_at=matched.created_at,
                thumbnail_url=f"/api/checks/{matched.id}/thumbnail",
                uploaded_by=matched.uploaded_by or "anonymous",
            )
        similarity = SimilarityBlock(
            top_score=check.similarity_top_score,
            tier=check.similarity_tier,
            match_count=check.similarity_match_count or 0,
            match=match,
            color=tiers.color_of(tiers.severity_of_similarity_tier(check.similarity_tier)),
        )

    return CheckResult(
        check_id=check.id,
        check_type=check.check_type,
        filename=check.filename,
        content_type=check.content_type,
        created_at=check.created_at,
        overall_tier=check.overall_tier,
        overall_color=tiers.color_of(check.overall_tier),
        image_url=f"/api/checks/{check.id}/image",
        thumbnail_url=f"/api/checks/{check.id}/thumbnail",
        uploaded_by=check.uploaded_by or "anonymous",
        nsfw=nsfw,
        similarity=similarity,
        explanation=_explanation_of(check),
        explained_at=check.explained_at,
    )
