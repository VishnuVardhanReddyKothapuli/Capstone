"""POST /api/moderate — the one endpoint that runs a check and writes a row."""

from __future__ import annotations

import logging
import re
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select

from app.config import settings
from app.deps import CurrentUser, DbSession
from app.models import Check
from app.schemas import CheckResult, check_to_result
from app.services import classifier, embedder, images, similarity, tiers

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["moderation"])

READ_CHUNK = 1 << 20  # 1 MiB
Mode = Literal["nsfw", "similarity", "both"]


def _read_upload(upload: UploadFile) -> bytes:
    """Read the upload with a hard size cap, so a huge file cannot exhaust RAM."""
    limit = settings.MAX_UPLOAD_BYTES
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = upload.file.read(READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds the {limit // (1024 * 1024)} MiB limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/moderate", response_model=CheckResult)
def moderate(
    current_user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File(description="Image or GIF to check.")],
    mode: Annotated[Mode, Form(description="Which checks to run.")] = "both",
) -> CheckResult:
    """Classify and/or fingerprint one upload, persist it, and return the verdict.

    Defined as a sync endpoint on purpose: FastAPI runs it in a worker thread, so
    the CPU-bound PIL decode and model inference never block the event loop.
    """
    data = _read_upload(file)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty upload.")

    # Strip path separators, control characters, and collapse whitespace in the
    # filename so it never ends up carrying directory traversal payloads or
    # invisible characters into logs or the database.
    raw_name = (file.filename or "upload")[:512]
    safe_name = re.sub(r'[\x00-\x1f\\/:]', '', raw_name).strip() or "upload"

    try:
        decoded = images.decode(data)
    except images.UnsupportedImageError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc

    thumbnail = images.make_thumbnail(decoded.frames[0])

    nsfw_result = None
    if mode in ("nsfw", "both"):
        try:
            nsfw_result = classifier.classify(decoded.frames, decoded.frame_count)
        except Exception:  # model download/load failure, bad checkpoint, OOM
            logger.exception("NSFW classification failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Classification service is temporarily unavailable."
            )

    # Embeddings are only computed when the mode asks for similarity, so an
    # NSFW-only check never pays for loading CLIP. The flip side, by design: an
    # NSFW-only upload is not added to the corpus and cannot be matched later.
    embedding: list[float] | None = None
    sim_result = None
    if mode in ("similarity", "both"):
        try:
            embedding = embedder.embed(decoded.frames)
        except Exception:
            logger.exception("CLIP embedding failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Embedding service is temporarily unavailable."
            )
        try:
            sim_result = similarity.analyse(embedding, db, current_user.id)
        except Exception:
            logger.exception("Vector-store query failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Similarity service is temporarily unavailable."
            )

    check = Check(
        filename=safe_name,
        content_type=decoded.content_type,
        image_blob=data,
        thumbnail_blob=thumbnail,
        user_id=current_user.id,
        uploaded_by=current_user.username,
        check_type=mode,
        overall_tier=tiers.worst_tier(
            nsfw_result.tier if nsfw_result else None,
            sim_result.severity if sim_result else None,
        ),
    )
    if nsfw_result is not None:
        check.nsfw_score = nsfw_result.nsfw_score
        check.safe_score = nsfw_result.safe_score
        check.nsfw_tier = nsfw_result.tier
        check.nsfw_threshold = nsfw_result.threshold
        check.frames_analyzed = nsfw_result.frames_analyzed
        check.frame_count = nsfw_result.frame_count
    if sim_result is not None:
        check.similarity_top_score = sim_result.top_score
        check.similarity_tier = sim_result.tier
        check.similarity_match_check_id = sim_result.match_check_id
        check.similarity_match_count = sim_result.match_count

    db.add(check)
    db.commit()
    db.refresh(check)

    if embedding is not None:
        try:
            # Registered only after the commit, so the Chroma id is the real row id.
            similarity.register(check, embedding)
        except Exception:
            # The verdict is already durable in SQL; losing the vector only means
            # this image will not be matchable, which is not worth failing on.
            logger.exception("Failed to register embedding for check %s", check.id)

    return check_to_result(check)


def _get_owned_check(check_id: int, user_id: int, db: DbSession) -> Check:
    check = db.execute(select(Check).where(Check.id == check_id, Check.user_id == user_id)).scalar_one_or_none()
    if check is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return check


@router.get(
    "/checks/{check_id}/thumbnail",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
def get_thumbnail(check_id: int, current_user: CurrentUser, db: DbSession) -> Response:
    """Thumbnail bytes, readable by any signed-in user.

    Deliberately not owner-scoped: a similarity result has to be able to show a
    thumbnail of the image it matched, and that image often belongs to someone
    else. The full-size original stays owner-only — see `get_image` below.
    """
    # Any authenticated user may read thumbnails; ownership is NOT checked here.
    check = db.get(Check, check_id)
    if check is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return Response(
        content=check.thumbnail_blob,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get(
    "/checks/{check_id}/image",
    response_class=Response,
    responses={200: {"content": {"image/*": {}}}},
)
def get_image(check_id: int, current_user: CurrentUser, db: DbSession) -> Response:
    """Original bytes, restricted to the account that uploaded them."""
    check = _get_owned_check(check_id, current_user.id, db)
    return Response(
        content=check.image_blob,
        media_type=check.content_type or "application/octet-stream",
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{check.id}"',
        },
    )
