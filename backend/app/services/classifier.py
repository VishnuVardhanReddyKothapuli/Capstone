"""NSFW classification via Falconsai/nsfw_image_detection (binary ViT).

The model exposes exactly two labels — `nsfw` and `normal` — so everything this
module reports is either a raw softmax value or an explicitly documented
aggregation over sampled frames. Nothing is invented from the binary score.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from PIL import Image

from app.config import settings
from app.services import tiers

_pipeline: Any = None
_load_lock = threading.Lock()


@dataclass(frozen=True)
class NsfwResult:
    """The five values the NSFW result card shows."""

    nsfw_score: float
    safe_score: float
    tier: str
    threshold: float
    frames_analyzed: int
    frame_count: int


def get_pipeline() -> Any:
    """Lazily build the HF pipeline. First call downloads/loads ~350 MB."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    with _load_lock:
        if _pipeline is None:
            # Imported here, not at module scope: pulling in transformers/torch
            # costs seconds, and the API should start without paying that until
            # the first real check comes in.
            import torch
            from transformers import pipeline as hf_pipeline

            _pipeline = hf_pipeline(
                task="image-classification",
                model=settings.NSFW_MODEL,
                # String form, accepted by both transformers 4.x and 5.x.
                device="cuda" if torch.cuda.is_available() else "cpu",
            )
    return _pipeline


def is_loaded() -> bool:
    return _pipeline is not None


def _nsfw_probability(predictions: list[dict[str, Any]]) -> float:
    """Pull the `nsfw` probability out of one frame's predictions."""
    by_label = {str(p["label"]).strip().lower(): float(p["score"]) for p in predictions}
    if "nsfw" in by_label:
        return by_label["nsfw"]
    # Defensive: tolerate a checkpoint that only names the safe class.
    for safe_label in ("normal", "safe", "sfw"):
        if safe_label in by_label:
            return 1.0 - by_label[safe_label]
    raise RuntimeError(
        f"{settings.NSFW_MODEL} returned unexpected labels: {sorted(by_label)}"
    )


def classify(frames: list[Image.Image], frame_count: int | None = None) -> NsfwResult:
    """Score sampled frames and band the result.

    Animations aggregate with **max**: a GIF is treated as unsafe if any sampled
    frame is unsafe, which is the conservative choice for moderation. `safe_score`
    is taken as the complement of that same frame's score, so the pair stays a
    real two-class softmax instead of mixing numbers from different frames.
    """
    if not frames:
        raise ValueError("classify() needs at least one frame")

    pipe = get_pipeline()
    outputs = pipe(frames)
    # transformers returns a flat list for a single image, nested for a batch.
    if frames and outputs and isinstance(outputs[0], dict):
        outputs = [outputs]

    nsfw = max(_nsfw_probability(frame_preds) for frame_preds in outputs)
    nsfw = min(max(nsfw, 0.0), 1.0)

    return NsfwResult(
        nsfw_score=nsfw,
        safe_score=1.0 - nsfw,
        tier=tiers.classify_nsfw_tier(nsfw),
        threshold=settings.NSFW_EXPLICIT_THRESHOLD,
        frames_analyzed=len(frames),
        frame_count=frame_count if frame_count is not None else len(frames),
    )
