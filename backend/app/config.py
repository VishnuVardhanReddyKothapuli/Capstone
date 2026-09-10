"""Application settings, loaded from environment / backend/.env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/  — every relative path in the config resolves against this, so the
# app behaves the same no matter which directory uvicorn was launched from.
BASE_DIR = Path(__file__).resolve().parent.parent

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Sentinal"
    APP_VERSION: str = "1.0.0"

    # ---- Storage -----------------------------------------------------------
    # Relational store: image blobs, thumbnails, verdicts, users. No embeddings.
    DATABASE_URL: str = f"sqlite:///{(BASE_DIR / 'sentinal.db').as_posix()}"
    # Vector store: CLIP embeddings only.
    CHROMA_PERSIST_DIR: str = str(BASE_DIR / "chroma_db")
    CHROMA_COLLECTION: str = "image_embeddings"

    # ---- Auth --------------------------------------------------------------
    JWT_SECRET: str = DEV_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 720
    JWT_ISSUER: str = "sentinal"
    JWT_AUDIENCE: str = "sentinal-web"
    # Empty disables the admin area. Never expose this configuration to clients.
    ADMIN_EMAIL: str = ""
    ENVIRONMENT: str = "development"

    # ---- NSFW classification ----------------------------------------------
    # Falconsai is a binary ViT classifier: labels are exactly {normal, nsfw}.
    NSFW_MODEL: str = "Falconsai/nsfw_image_detection"
    # nsfw_score >= EXPLICIT              -> explicit (red)
    # SUGGESTIVE <= nsfw_score < EXPLICIT -> suggestive (amber)
    # nsfw_score <  SUGGESTIVE            -> safe (green)
    NSFW_EXPLICIT_THRESHOLD: float = 0.70
    NSFW_SUGGESTIVE_THRESHOLD: float = 0.40

    # ---- Similarity --------------------------------------------------------
    CLIP_MODEL: str = "openai/clip-vit-base-patch32"
    SIMILARITY_TOP_K: int = 5
    # How many neighbours to scan when counting matches above the floor. The
    # reported match_count saturates here rather than scanning the whole index.
    SIMILARITY_COUNT_K: int = 50
    SIM_IDENTICAL_THRESHOLD: float = 0.98
    SIM_NEAR_DUPLICATE_THRESHOLD: float = 0.92
    SIM_SIMILAR_THRESHOLD: float = 0.80
    # Cosine score below which a neighbour is not counted as a match at all.
    SIM_MATCH_FLOOR: float = 0.60

    # ---- Media handling ----------------------------------------------------
    MAX_GIF_FRAMES: int = 16
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024  # 10 MiB
    THUMBNAIL_SIZE: int = 256

    # ---- Gemini explanations -----------------------------------------------
    # Optional. Empty key = the feature is off and the endpoint answers 503.
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"
    GEMINI_API_BASE: str = "https://generativelanguage.googleapis.com/v1beta"
    GEMINI_TIMEOUT_SECONDS: float = 45.0
    # The frame is downscaled to this longest edge before it is sent, which keeps
    # the request small without hiding anything a moderator would need to see.
    GEMINI_MAX_IMAGE_EDGE: int = 1024

    # ---- Serving -----------------------------------------------------------
    # Comma-separated. Only needed while the Vite dev server is on another port.
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Built frontend (frontend/dist) is served from / when this directory exists.
    FRONTEND_DIST: str = str(BASE_DIR.parent / "frontend" / "dist")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def jwt_secret_is_default(self) -> bool:
        return self.JWT_SECRET == DEV_JWT_SECRET

    @property
    def gemini_configured(self) -> bool:
        """Never expose the key itself — only whether one is present."""
        return bool(self.GEMINI_API_KEY.strip())

    @property
    def admin_email(self) -> str:
        return self.ADMIN_EMAIL.strip().casefold()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
