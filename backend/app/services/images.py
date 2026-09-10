"""Decoding uploads, sampling GIF keyframes, and building History thumbnails."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from app.config import settings

# Refuse obviously hostile pixel counts before PIL tries to allocate them.
MAX_PIXELS = 50_000_000

MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "JPEG2000": "image/jp2",
    "PNG": "image/png",
    "GIF": "image/gif",
    "WEBP": "image/webp",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
    "ICO": "image/x-icon",
}


class UnsupportedImageError(ValueError):
    """Raised when the upload is not a still image or animation PIL can read."""


@dataclass
class Decoded:
    frames: list[Image.Image]  # sampled RGB keyframes
    frame_count: int           # total frames in the file
    content_type: str          # sniffed from the bytes, not from the client header
    width: int
    height: int

    @property
    def is_animated(self) -> bool:
        return self.frame_count > 1


def _keyframe_indices(total_frames: int, max_frames: int) -> list[int]:
    """Evenly spaced frame indices, always including the first and last frame."""
    if total_frames <= 1:
        return [0]
    if total_frames <= max_frames:
        return list(range(total_frames))
    step = (total_frames - 1) / (max_frames - 1)
    return sorted({round(i * step) for i in range(max_frames)})


def decode(data: bytes, max_frames: int | None = None) -> Decoded:
    """Decode an upload into RGB frames plus the metadata the API records.

    A still image yields one frame; an animation yields up to `max_frames` evenly
    spaced keyframes, so a long GIF costs a bounded number of model passes.
    """
    limit = settings.MAX_GIF_FRAMES if max_frames is None else max_frames
    try:
        image = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError) as exc:
        raise UnsupportedImageError("File is not a readable image or animation.") from exc

    width, height = image.size
    if width * height > MAX_PIXELS:
        raise UnsupportedImageError(f"Image is too large to process ({width}x{height} px).")

    fmt = (image.format or "").upper()
    total = int(getattr(image, "n_frames", 1) or 1)

    frames: list[Image.Image] = []
    for index in _keyframe_indices(total, limit):
        try:
            image.seek(index)
        except EOFError:  # truncated animation — keep whatever decoded cleanly
            break
        frames.append(image.convert("RGB"))

    if not frames:
        raise UnsupportedImageError("No decodable frames in file.")

    return Decoded(
        frames=frames,
        frame_count=total,
        content_type=MIME_BY_FORMAT.get(fmt, f"image/{fmt.lower()}" if fmt else "image/unknown"),
        width=width,
        height=height,
    )


def make_thumbnail(frame: Image.Image, size: int | None = None) -> bytes:
    """Downscale-to-fit JPEG bytes, never upscaling and never cropping.

    Used for the stored History thumbnail at `THUMBNAIL_SIZE`, and again at a
    larger edge to shrink a frame before it is sent to the Gemini explainer.
    """
    edge = settings.THUMBNAIL_SIZE if size is None else size
    thumb = frame.copy()
    thumb.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    thumb.save(out, format="JPEG", quality=82, optimize=True)
    return out.getvalue()
