"""GET /api/models — real config for the "Models & Tech Stack" view."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app import __version__
from app.config import settings
from app.deps import CurrentUser
from app.schemas import ModelInfo
from app.services import classifier, embedder, explainer, vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["meta"])


def _relational_backend() -> str:
    """Dialect name only — DATABASE_URL can carry a password."""
    scheme = settings.DATABASE_URL.split("://", 1)[0]
    dialect = scheme.split("+", 1)[0].lower()
    return {"sqlite": "SQLite", "mysql": "MySQL", "postgresql": "PostgreSQL"}.get(
        dialect, dialect or "unknown"
    )


@router.get("/models", response_model=ModelInfo)
def model_info(current_user: CurrentUser) -> ModelInfo:
    """Everything the frontend needs so the stack page is never hardcoded copy."""
    try:
        stored_vectors = vector_store.count()
    except Exception:
        logger.exception("Could not read the Chroma collection count")
        stored_vectors = 0

    return ModelInfo(
        nsfw_model=settings.NSFW_MODEL,
        nsfw_labels=["normal", "nsfw"],
        nsfw_explicit_threshold=settings.NSFW_EXPLICIT_THRESHOLD,
        nsfw_suggestive_threshold=settings.NSFW_SUGGESTIVE_THRESHOLD,
        nsfw_model_loaded=classifier.is_loaded(),
        embedding_model=settings.CLIP_MODEL,
        embedding_dim=embedder.EMBEDDING_DIM,
        embedding_model_loaded=embedder.is_loaded(),
        vector_store="ChromaDB (persistent)",
        vector_store_collection=settings.CHROMA_COLLECTION,
        vector_store_count=stored_vectors,
        relational_store=f"{_relational_backend()} via SQLAlchemy 2",
        backend="FastAPI",
        max_gif_frames=settings.MAX_GIF_FRAMES,
        max_upload_bytes=settings.MAX_UPLOAD_BYTES,
        similarity_bands={
            "identical": settings.SIM_IDENTICAL_THRESHOLD,
            "near_duplicate": settings.SIM_NEAR_DUPLICATE_THRESHOLD,
            "similar": settings.SIM_SIMILAR_THRESHOLD,
            "match_floor": settings.SIM_MATCH_FLOOR,
        },
        explainer_model=settings.GEMINI_MODEL,
        # The boolean only. The key itself never leaves the server.
        explainer_configured=explainer.is_configured(),
        app_version=__version__,
        environment=settings.ENVIRONMENT,
        deployment="ASGI (Uvicorn-compatible)",
    )
