"""CLIP image embeddings (openai/clip-vit-base-patch32, 512-dim).

Vectors are L2-normalised here so a Chroma cosine query returns a score that is
directly comparable to the bands in `tiers.classify_similarity_tier`.
"""

from __future__ import annotations

import threading
from typing import Any

from PIL import Image

from app.config import settings

EMBEDDING_DIM = 512

_model: Any = None
_processor: Any = None
_device: Any = None
_load_lock = threading.Lock()


def get_model() -> tuple[Any, Any, Any]:
    """Lazily load CLIP. Returns `(model, image_processor, device)`."""
    global _model, _processor, _device
    if _model is not None:
        return _model, _processor, _device
    with _load_lock:
        if _model is None:
            # Deferred for the same reason as in classifier.py: keep startup cheap.
            import torch
            from transformers import CLIPImageProcessor, CLIPModel

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            model = CLIPModel.from_pretrained(settings.CLIP_MODEL).to(device)
            model.eval()
            # CLIPImageProcessor, not AutoImageProcessor: the Auto class resolves
            # to the torchvision backend and hard-fails without it, while this one
            # falls back to the Pillow implementation. Install torchvision (see
            # requirements.txt) to get the faster tensor path.
            _processor = CLIPImageProcessor.from_pretrained(settings.CLIP_MODEL)
            _device = device
            _model = model
    return _model, _processor, _device


def is_loaded() -> bool:
    return _model is not None


def embed(frames: list[Image.Image]) -> list[float]:
    """One 512-dim unit vector for an image or animation.

    Multi-frame input is reduced by averaging the per-frame unit vectors and
    renormalising, which keeps a GIF close to visually identical GIFs without
    letting one outlier frame dominate.
    """
    if not frames:
        raise ValueError("embed() needs at least one frame")

    import torch

    model, processor, device = get_model()
    inputs = processor(images=frames, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model.get_image_features(**inputs)

    # transformers 5 returns BaseModelOutputWithPooling from get_image_features,
    # with the projected image features in `pooler_output`; older versions handed
    # back the tensor itself.
    features = getattr(outputs, "pooler_output", outputs)
    if features.shape[-1] != EMBEDDING_DIM:
        raise RuntimeError(
            f"{settings.CLIP_MODEL} produced {features.shape[-1]}-dim features, but the "
            f"Chroma collection stores {EMBEDDING_DIM}. Update EMBEDDING_DIM and re-index."
        )

    features = features / features.norm(p=2, dim=-1, keepdim=True)
    pooled = features.mean(dim=0)
    pooled = pooled / pooled.norm(p=2)
    return pooled.detach().cpu().tolist()
