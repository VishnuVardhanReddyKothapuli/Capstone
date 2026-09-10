"""Decoding, GIF keyframe sampling, and thumbnail generation."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.services import images
from tests.conftest import make_gif, make_png


def test_still_image_is_one_frame() -> None:
    decoded = images.decode(make_png(size=(30, 20)))
    assert len(decoded.frames) == 1
    assert decoded.frame_count == 1
    assert decoded.is_animated is False
    assert decoded.content_type == "image/png"
    assert (decoded.width, decoded.height) == (30, 20)
    assert decoded.frames[0].mode == "RGB"


def test_content_type_is_sniffed_not_trusted() -> None:
    """A .png filename on GIF bytes must still be recorded as a GIF."""
    decoded = images.decode(make_gif([(1, 2, 3), (4, 5, 6)]))
    assert decoded.content_type == "image/gif"


def test_long_animation_is_capped_and_keeps_the_ends() -> None:
    frames = [(index * 8 % 256, 40, 90) for index in range(30)]
    decoded = images.decode(make_gif(frames, size=(16, 16)), max_frames=16)

    assert decoded.frame_count == 30
    assert len(decoded.frames) == 16
    assert decoded.is_animated is True


def test_short_animation_is_sampled_whole() -> None:
    decoded = images.decode(make_gif([(0, 0, 0), (9, 9, 9), (250, 0, 0)]), max_frames=16)
    assert decoded.frame_count == 3
    assert len(decoded.frames) == 3


@pytest.mark.parametrize(
    ("total", "cap", "expected"),
    [
        (1, 16, [0]),
        (4, 16, [0, 1, 2, 3]),
        (16, 16, list(range(16))),
        (3, 2, [0, 2]),
        (100, 5, [0, 25, 50, 74, 99]),
    ],
)
def test_keyframe_indices(total: int, cap: int, expected: list[int]) -> None:
    assert images._keyframe_indices(total, cap) == expected


def test_thumbnail_fits_the_box_and_is_jpeg() -> None:
    source = Image.new("RGB", (900, 300), (10, 200, 120))
    data = images.make_thumbnail(source, size=128)

    thumb = Image.open(io.BytesIO(data))
    assert thumb.format == "JPEG"
    assert max(thumb.size) == 128
    assert thumb.size == (128, 43)  # 300 * 128 / 900, rounded
    # The original is untouched.
    assert source.size == (900, 300)


def test_unreadable_upload_raises() -> None:
    with pytest.raises(images.UnsupportedImageError):
        images.decode(b"definitely not an image")
    with pytest.raises(images.UnsupportedImageError):
        images.decode(b"")
