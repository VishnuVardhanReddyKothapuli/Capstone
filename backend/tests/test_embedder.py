"""Pooling and normalisation in `embedder.embed`, with CLIP itself stubbed out.

These are regression tests for the shape of what `get_image_features` hands
back: transformers 5 returns a `BaseModelOutputWithPooling` whose
`pooler_output` holds the projected features, while older releases returned the
tensor directly. `embed()` has to cope with both, and no other test can catch a
break here because the rest of the suite fakes `embed` wholesale.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest
import torch
from PIL import Image

from app.services import embedder


class FakeInputs(dict):
    """Stand-in for `BatchFeature`: unpacks with `**` and absorbs `.to(device)`."""

    def to(self, device: Any) -> FakeInputs:  # noqa: ARG002 - signature parity only
        return self


class FakeProcessor:
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def __call__(self, images: list[Image.Image], return_tensors: str) -> FakeInputs:
        assert return_tensors == "pt"
        self.batch_sizes.append(len(images))
        return FakeInputs(pixel_values=torch.zeros(len(images), 3, 8, 8))


def install(monkeypatch: pytest.MonkeyPatch, features: torch.Tensor, *, wrapped: bool):
    """Point `embed()` at a model that returns exactly `features`.

    `wrapped=True` mimics transformers 5 (a pooling output object), `False`
    mimics the older bare-tensor return.
    """
    processor = FakeProcessor()

    def get_image_features(**_inputs: Any) -> Any:
        return SimpleNamespace(pooler_output=features) if wrapped else features

    model = SimpleNamespace(get_image_features=get_image_features)
    monkeypatch.setattr(
        embedder, "get_model", lambda: (model, processor, torch.device("cpu"))
    )
    return processor


def frames(count: int) -> list[Image.Image]:
    return [Image.new("RGB", (8, 8), (index * 30 % 256, 40, 90)) for index in range(count)]


def row(*leading: float) -> list[float]:
    """One 512-wide feature row whose first values are `leading`."""
    return list(leading) + [0.0] * (embedder.EMBEDDING_DIM - len(leading))


@pytest.mark.parametrize("wrapped", [True, False], ids=["pooler_output", "bare_tensor"])
def test_both_return_shapes_are_understood(
    monkeypatch: pytest.MonkeyPatch, wrapped: bool
) -> None:
    install(monkeypatch, torch.tensor([row(3.0, 4.0)]), wrapped=wrapped)

    vector = embedder.embed(frames(1))

    assert len(vector) == embedder.EMBEDDING_DIM
    # 3-4-5 triangle: normalising the row must give exactly 0.6 / 0.8.
    assert vector[0] == pytest.approx(0.6)
    assert vector[1] == pytest.approx(0.8)


def test_result_is_a_unit_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chroma's cosine score is only comparable to the tier bands if this holds."""
    install(monkeypatch, torch.tensor([row(-11.0, 0.5, 7.25)]), wrapped=True)

    vector = embedder.embed(frames(1))

    assert math.sqrt(sum(value * value for value in vector)) == pytest.approx(1.0)


def test_frames_are_normalised_before_averaging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every frame gets one equal vote, whatever its raw feature magnitude.

    The two rows here are orthogonal with lengths 3 and 4. Pooling the raw rows
    would land on 0.6 / 0.8; pooling the *unit* rows lands on 1/root-2 each.
    """
    processor = install(
        monkeypatch, torch.tensor([row(3.0, 0.0), row(0.0, 4.0)]), wrapped=True
    )

    vector = embedder.embed(frames(2))

    assert vector[0] == pytest.approx(1 / math.sqrt(2))
    assert vector[1] == pytest.approx(1 / math.sqrt(2))
    assert math.sqrt(sum(value * value for value in vector)) == pytest.approx(1.0)
    # One processor call for the whole animation, not one per frame.
    assert processor.batch_sizes == [2]


def test_wrong_width_is_rejected_with_a_useful_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(monkeypatch, torch.ones(1, 768), wrapped=True)

    with pytest.raises(RuntimeError, match="768-dim"):
        embedder.embed(frames(1))


def test_no_frames_is_a_value_error() -> None:
    with pytest.raises(ValueError):
        embedder.embed([])
