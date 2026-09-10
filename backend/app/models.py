"""SQL schema.

Division of responsibility:
  * SQL (here)  — users, the checked image bytes, its thumbnail, and verdicts.
  * ChromaDB    — CLIP embeddings. Deliberately *no* embedding column below.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# 16 MiB: SQLAlchemy maps this length to MySQL MEDIUMBLOB (plain BLOB caps at
# 64 KiB, which would silently truncate uploads). Ignored by SQLite.
BLOB_LEN = 16_777_215

CHECK_TYPES = ("nsfw", "similarity", "both")
NSFW_TIERS = ("safe", "suggestive", "explicit")
SIMILARITY_TIERS = ("Identical", "Near-Duplicate", "Similar", "Slightly Similar", "Unique")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    checks: Mapped[list["Check"]] = relationship(
        back_populates="user", foreign_keys="Check.user_id"
    )


class Check(Base):
    """One moderation run on one uploaded file."""

    __tablename__ = "checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # ---- The file ----------------------------------------------------------
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    image_blob: Mapped[bytes] = mapped_column(LargeBinary(BLOB_LEN), nullable=False)
    thumbnail_blob: Mapped[bytes] = mapped_column(LargeBinary(BLOB_LEN), nullable=False)

    # ---- Who / when / what ------------------------------------------------
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Snapshot of the username so History still reads correctly if a user is
    # ever removed.
    uploaded_by: Mapped[str] = mapped_column(String(64), default="anonymous", nullable=False)
    check_type: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    # ---- NSFW verdict (null when check_type == "similarity") --------------
    # Falconsai is binary, so these two are the model's real softmax outputs
    # and nothing else is invented from them.
    nsfw_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    safe_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    nsfw_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Threshold in force at the time of the check, so a historical verdict stays
    # explainable after someone edits .env.
    nsfw_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    frames_analyzed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ---- Similarity verdict (null when check_type == "nsfw") --------------
    similarity_top_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    similarity_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    similarity_match_check_id: Mapped[int | None] = mapped_column(
        ForeignKey("checks.id", ondelete="SET NULL"), nullable=True
    )
    similarity_match_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ---- Worst-of-both ----------------------------------------------------
    overall_tier: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    # ---- Gemini explanation (null until someone asks for one) --------------
    # Stored as the JSON of one `explainer.Explanation`, so the reasoning is part
    # of the audit trail and re-opening a history row costs no API call. Kept
    # opaque on purpose: none of it is queried, and the shape belongs to the
    # explainer service rather than to the schema.
    explanation_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    explained_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[Optional["User"]] = relationship(back_populates="checks", foreign_keys=[user_id])
    similarity_match: Mapped[Optional["Check"]] = relationship(
        "Check",
        remote_side=[id],
        foreign_keys=[similarity_match_check_id],
        uselist=False,
    )


# History is always "newest first", optionally filtered by type.
Index("ix_checks_created_at_desc", Check.created_at.desc())
Index("ix_checks_type_created", Check.check_type, Check.created_at.desc())
