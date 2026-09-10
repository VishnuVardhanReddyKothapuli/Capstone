"""Tier banding: turns raw model numbers into the red / amber / green verdicts.

Pure functions, no I/O — this is the file the tests lean on hardest.
"""

from __future__ import annotations

from app.config import settings

# Severity vocabulary shared by both checks, ordered worst-last.
TIER_SAFE = "safe"
TIER_SUGGESTIVE = "suggestive"
TIER_EXPLICIT = "explicit"

SEVERITY_ORDER: dict[str, int] = {TIER_SAFE: 0, TIER_SUGGESTIVE: 1, TIER_EXPLICIT: 2}
COLOR_BY_TIER: dict[str, str] = {TIER_SAFE: "green", TIER_SUGGESTIVE: "amber", TIER_EXPLICIT: "red"}

# Similarity has its own 5-band label set, which then collapses onto the three
# severities above so a "both" check can be compared apples-to-apples.
SIM_IDENTICAL = "Identical"
SIM_NEAR_DUPLICATE = "Near-Duplicate"
SIM_SIMILAR = "Similar"
SIM_SLIGHTLY_SIMILAR = "Slightly Similar"
SIM_UNIQUE = "Unique"

SEVERITY_BY_SIM_TIER: dict[str, str] = {
    SIM_IDENTICAL: TIER_EXPLICIT,       # red    — almost certainly a re-upload
    SIM_NEAR_DUPLICATE: TIER_EXPLICIT,  # red
    SIM_SIMILAR: TIER_SUGGESTIVE,       # amber  — worth a human look
    SIM_SLIGHTLY_SIMILAR: TIER_SAFE,    # green
    SIM_UNIQUE: TIER_SAFE,              # green
}


def classify_nsfw_tier(
    nsfw_score: float,
    *,
    explicit_threshold: float | None = None,
    suggestive_threshold: float | None = None,
) -> str:
    """Band Falconsai's single `nsfw` probability into safe / suggestive / explicit.

    Falconsai only emits two classes, so the amber band is a genuine confidence
    window ("the model is unsure") rather than a made-up content category.
    """
    explicit = (
        settings.NSFW_EXPLICIT_THRESHOLD if explicit_threshold is None else explicit_threshold
    )
    suggestive = (
        settings.NSFW_SUGGESTIVE_THRESHOLD
        if suggestive_threshold is None
        else suggestive_threshold
    )

    if nsfw_score >= explicit:
        return TIER_EXPLICIT
    if nsfw_score >= suggestive:
        return TIER_SUGGESTIVE
    return TIER_SAFE


def classify_similarity_tier(top_score: float | None) -> str:
    """Band the best cosine score from Chroma into one of five labels.

    `None` means the vector store held nothing to compare against yet.
    """
    if top_score is None:
        return SIM_UNIQUE
    if top_score >= settings.SIM_IDENTICAL_THRESHOLD:
        return SIM_IDENTICAL
    if top_score >= settings.SIM_NEAR_DUPLICATE_THRESHOLD:
        return SIM_NEAR_DUPLICATE
    if top_score >= settings.SIM_SIMILAR_THRESHOLD:
        return SIM_SIMILAR
    if top_score >= settings.SIM_MATCH_FLOOR:
        return SIM_SLIGHTLY_SIMILAR
    return SIM_UNIQUE


def severity_of_similarity_tier(sim_tier: str) -> str:
    return SEVERITY_BY_SIM_TIER.get(sim_tier, TIER_SAFE)


def worst_tier(*tiers: str | None) -> str:
    """Worst-of-both, used for `overall_tier` when check_type == "both"."""
    present = [t for t in tiers if t in SEVERITY_ORDER]
    if not present:
        return TIER_SAFE
    return max(present, key=lambda t: SEVERITY_ORDER[t])


def color_of(tier: str) -> str:
    return COLOR_BY_TIER.get(tier, "green")
