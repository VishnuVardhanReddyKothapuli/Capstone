"""Tier banding — the rules that turn model numbers into red / amber / green."""

from __future__ import annotations

import pytest

from app.services import tiers


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.00, "safe"),
        (0.39, "safe"),
        (0.40, "suggestive"),  # inclusive lower edge of the amber band
        (0.69, "suggestive"),
        (0.70, "explicit"),  # inclusive lower edge of the red band
        (1.00, "explicit"),
    ],
)
def test_nsfw_bands(score: float, expected: str) -> None:
    assert tiers.classify_nsfw_tier(score) == expected


def test_nsfw_thresholds_are_overridable() -> None:
    assert (
        tiers.classify_nsfw_tier(0.5, explicit_threshold=0.4, suggestive_threshold=0.2)
        == "explicit"
    )


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (1.00, "Identical"),
        (0.98, "Identical"),
        (0.97, "Near-Duplicate"),
        (0.92, "Near-Duplicate"),
        (0.91, "Similar"),
        (0.80, "Similar"),
        (0.79, "Slightly Similar"),
        (0.60, "Slightly Similar"),
        (0.59, "Unique"),
        (0.00, "Unique"),
    ],
)
def test_similarity_bands(score: float, expected: str) -> None:
    assert tiers.classify_similarity_tier(score) == expected


def test_empty_corpus_is_unique() -> None:
    assert tiers.classify_similarity_tier(None) == "Unique"


@pytest.mark.parametrize(
    ("sim_tier", "severity"),
    [
        ("Identical", "explicit"),
        ("Near-Duplicate", "explicit"),
        ("Similar", "suggestive"),
        ("Slightly Similar", "safe"),
        ("Unique", "safe"),
    ],
)
def test_similarity_severity_mapping(sim_tier: str, severity: str) -> None:
    assert tiers.severity_of_similarity_tier(sim_tier) == severity


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (("safe", "safe"), "safe"),
        (("safe", "suggestive"), "suggestive"),
        (("suggestive", "explicit"), "explicit"),
        (("explicit", None), "explicit"),
        ((None, None), "safe"),
        ((None, "suggestive"), "suggestive"),
    ],
)
def test_worst_tier(given: tuple, expected: str) -> None:
    assert tiers.worst_tier(*given) == expected


def test_colors() -> None:
    assert tiers.color_of("safe") == "green"
    assert tiers.color_of("suggestive") == "amber"
    assert tiers.color_of("explicit") == "red"
