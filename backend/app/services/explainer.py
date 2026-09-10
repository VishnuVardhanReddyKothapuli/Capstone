"""Second-opinion explanations from Gemini: *why* is this safe or unsafe.

Falconsai answers "how likely is this NSFW" with one number and no reasoning.
This module asks a multimodal model to describe what is visibly present, read any
embedded text, and say in words whether the media may be published — so the card
can show a reason next to the score.

Independent of the classifier on purpose: it is a cross-check, not an input to
the tier. If the two disagree, the card shows both and lets a human decide.

Nothing here runs unless `GEMINI_API_KEY` is set, and no request is made until a
signed-in owner explicitly asks for one.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from PIL import Image

from app.config import settings
from app.services import images

logger = logging.getLogger(__name__)

# The five categories the model must choose between, worst-last within a rank.
CLASSES: tuple[str, ...] = ("safe", "suggestive", "nsfw", "violent", "hate")

# Only `safe` may be published (rule 7), so everything else shares one rank: the
# comparison this drives is "which of two labels is the less publishable", not a
# ranking of harm between nsfw, violent and hate.
_SEVERITY: dict[str, int] = {"safe": 0, "suggestive": 1, "nsfw": 2, "violent": 2, "hate": 2}

# Bounds on stored free text, so one verbose answer cannot bloat the row.
MAX_TEXT = 4000
MAX_PROSE = 1200

PROMPT = """Analyze the supplied image or video frame. Your job is to describe \
what is visibly present and decide whether it is safe to publish on \
general-audience social platforms.
Check for:

* nudity, sexual activity, exposed intimate body parts, fetish content, or sexually suggestive posing;
* violence, injury, blood, gore, weapons used to harm, or disturbing scenes;
* hate symbols, slurs, targeted harassment, extremist content, or discriminatory messages;
* all readable text in the media, including signs, captions, memes, labels, and screenshots.

Rules:

1. Use only visible evidence. Do not guess identities, intent, age, location, or context.
2. If a person may be under 18, is unclear in age, or the image is ambiguous, treat sexualized content conservatively as `nsfw`.
3. Do not give graphic sexual or violent details. Use brief, clinical wording.
4. A normal swimsuit, fitness, medical, art, or breastfeeding image is not automatically unsafe. Classify it as `suggestive` or `nsfw` only when visible context clearly supports it.
5. Any hateful or toxic embedded text can make otherwise benign media unsafe.
6. If uncertain between `safe` and another category, choose the non-safe category.
7. Only `safe` content is allowed to publish.

Return valid JSON only. Do not add Markdown, commentary, or extra keys.
{
"classification": "safe | suggestive | nsfw | violent | hate",
"confidence": 0.0,
"scores": {
"safe": 0.0,
"suggestive": 0.0,
"nsfw": 0.0,
"violent": 0.0,
"hate": 0.0
},
"detectedText": "all visible text, or null if none",
"textToxicity": 0.0,
"description": "A brief, neutral description of what is visibly shown.",
"explanation": "Brief reason for the classification and whether publishing should be blocked."
}
Score rules:

* Every score must be between 0 and 1.
* Scores must total approximately 1.
* `classification` must match the category with the highest score.
* `confidence` must equal the score for `classification`.
* For `safe`, state that publishing is allowed.
* For `suggestive`, `nsfw`, `violent`, or `hate`, state that publishing must be blocked.
"""

# Handed to the API as `responseSchema`, so the keys and types come back
# guaranteed and the prompt's "valid JSON only" is enforced by the transport
# rather than trusted.
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "classification": {"type": "STRING", "enum": list(CLASSES)},
        "confidence": {"type": "NUMBER"},
        "scores": {
            "type": "OBJECT",
            "properties": {name: {"type": "NUMBER"} for name in CLASSES},
            "required": list(CLASSES),
        },
        "detectedText": {"type": "STRING", "nullable": True},
        "textToxicity": {"type": "NUMBER"},
        "description": {"type": "STRING"},
        "explanation": {"type": "STRING"},
    },
    "required": [
        "classification",
        "confidence",
        "scores",
        "textToxicity",
        "description",
        "explanation",
    ],
    "propertyOrdering": [
        "classification",
        "confidence",
        "scores",
        "detectedText",
        "textToxicity",
        "description",
        "explanation",
    ],
}

# This *is* the moderation tool, so Gemini's own filters must not pre-empt it:
# an image that trips them is exactly the image a moderator needs described.
# Blocking is left to the classification we ask for, not to the transport.
SAFETY_SETTINGS: list[dict[str, str]] = [
    {"category": category, "threshold": "BLOCK_NONE"}
    for category in (
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
    )
]

_BLOCKED_FINISH_REASONS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY"}


class ExplainerNotConfigured(RuntimeError):
    """No GEMINI_API_KEY, so the feature is switched off."""


class ExplainerError(RuntimeError):
    """Gemini was reachable but the answer could not be used."""


class ExplainerBlocked(ExplainerError):
    """Gemini refused to analyse the media at all."""


class ExplainerTimeout(ExplainerError):
    """Gemini did not answer inside GEMINI_TIMEOUT_SECONDS."""


class ExplainerRateLimited(ExplainerError):
    """Gemini returned 429."""


@dataclass(frozen=True)
class Explanation:
    """A normalised, internally consistent verdict. Stored as JSON on the row."""

    classification: str
    confidence: float
    scores: dict[str, float]
    detected_text: str | None
    text_toxicity: float
    description: str
    explanation: str
    # Derived here, never parsed out of the model's prose (rule 7).
    publish_allowed: bool
    model: str
    frame_index: int
    frames_total: int
    # True when the model's own numbers were inconsistent and had to be fixed up.
    repaired: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_configured() -> bool:
    return settings.gemini_configured


def _number(value: Any) -> float:
    """A non-negative float, or 0.0 for anything unusable.

    No upper clamp: the scores are normalised by their total afterwards, so a
    model that answers in percentages (90, 5, 3, 1, 1) still rescales correctly
    instead of collapsing to a flat 1.0 across the board.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number < 0.0:  # NaN or negative
        return 0.0
    return number


def _unit(value: Any) -> float:
    """A standalone 0-1 figure that nothing else will rescale."""
    return min(_number(value), 1.0)


def _text(value: Any, limit: int) -> str:
    return "" if value is None else str(value).strip()[:limit]


def _detected_text(value: Any) -> str | None:
    """The prompt allows a literal null; some answers spell it as a word instead."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "no text", "no visible text"}:
        return None
    return text[:MAX_TEXT]


def normalise(payload: dict[str, Any], *, model: str, frame_index: int, frames_total: int) -> Explanation:
    """Turn a raw answer into a verdict that obeys the prompt's own score rules.

    The rules ask for scores in [0, 1] that total ~1, a `classification` equal to
    the argmax, and a `confidence` equal to that class's score. A model will
    occasionally break one of them, so rather than trust or reject the answer
    outright this repairs it deterministically and records that it did:

      * negative and unreadable scores become 0, then all five are rescaled to
        total 1 — which also fixes an answer given in percentages;
      * if the stated class disagrees with the argmax, the **less publishable** of
        the two wins, which is what rules 6 and 7 ask for;
      * `confidence` is recomputed from the winning class;
      * `publish_allowed` is derived from the class, never read from the prose.
    """
    raw_scores = payload.get("scores")
    scores = {
        name: _number(raw_scores.get(name) if isinstance(raw_scores, dict) else None)
        for name in CLASSES
    }

    total = sum(scores.values())
    if total <= 0:
        # With every score unusable there is nothing to normalise and nothing to
        # argue from. Inventing a verdict here would be worse than failing.
        raise ExplainerError("Gemini returned no usable scores.")

    repaired = False
    if abs(total - 1.0) > 0.02:
        scores = {name: value / total for name, value in scores.items()}
        repaired = True

    argmax = max(CLASSES, key=lambda name: scores[name])
    stated = str(payload.get("classification", "")).strip().lower()
    if stated not in CLASSES:
        classification = argmax
        repaired = True
    elif stated != argmax:
        classification = max((stated, argmax), key=lambda name: _SEVERITY[name])
        repaired = True
    else:
        classification = stated

    confidence = scores[classification]
    if abs(_unit(payload.get("confidence")) - confidence) > 0.02:
        repaired = True

    return Explanation(
        classification=classification,
        confidence=round(confidence, 4),
        scores={name: round(value, 4) for name, value in scores.items()},
        detected_text=_detected_text(payload.get("detectedText")),
        text_toxicity=_unit(payload.get("textToxicity")),
        description=_text(payload.get("description"), MAX_PROSE),
        explanation=_text(payload.get("explanation"), MAX_PROSE),
        publish_allowed=classification == "safe",
        model=model,
        frame_index=frame_index,
        frames_total=frames_total,
        repaired=repaired,
    )


def _request_body(image_b64: str) -> dict[str, Any]:
    """The rules go in systemInstruction; the user turn carries only the frame."""
    return {
        "systemInstruction": {"parts": [{"text": PROMPT}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}],
            }
        ],
        "generationConfig": {
            # Deterministic: the same image should not swing between bands on a
            # re-run, since the answer is stored as part of the audit trail.
            "temperature": 0.0,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
        "safetySettings": SAFETY_SETTINGS,
    }


def _first_json_part(body: dict[str, Any]) -> dict[str, Any]:
    """Pull the JSON object out of a generateContent response, or explain why not."""
    feedback = body.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        raise ExplainerBlocked(
            f"Gemini declined to analyse this image (blocked: {feedback['blockReason']})."
        )

    candidates = body.get("candidates") or []
    if not candidates:
        raise ExplainerError("Gemini returned no candidates.")

    candidate = candidates[0]
    finish = str(candidate.get("finishReason") or "").upper()
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()

    if not text:
        if finish in _BLOCKED_FINISH_REASONS:
            raise ExplainerBlocked(f"Gemini declined to analyse this image ({finish}).")
        raise ExplainerError(f"Gemini returned an empty answer (finishReason={finish or 'unset'}).")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        # responseMimeType should make this impossible; tolerate a fenced block.
        stripped = text.strip().strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            raise ExplainerError("Gemini did not return valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise ExplainerError("Gemini returned JSON that was not an object.")
    return parsed


def explain(frame: Image.Image, *, frame_index: int = 0, frames_total: int = 1) -> Explanation:
    """Send one frame to Gemini and return a normalised verdict.

    Raises `ExplainerNotConfigured` when no key is set; every other failure is an
    `ExplainerError` subclass carrying a message that is safe to show a user.
    """
    if not is_configured():
        raise ExplainerNotConfigured(
            "Gemini explanations are not configured. Set GEMINI_API_KEY in backend/.env."
        )

    jpeg = images.make_thumbnail(frame, size=settings.GEMINI_MAX_IMAGE_EDGE)
    body = _request_body(base64.b64encode(jpeg).decode("ascii"))
    url = f"{settings.GEMINI_API_BASE.rstrip('/')}/models/{settings.GEMINI_MODEL}:generateContent"

    try:
        response = httpx.post(
            url,
            json=body,
            # Header, not a query parameter: a key in the URL ends up in logs.
            headers={"x-goog-api-key": settings.GEMINI_API_KEY, "Content-Type": "application/json"},
            timeout=settings.GEMINI_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise ExplainerTimeout(
            f"Gemini did not answer within {settings.GEMINI_TIMEOUT_SECONDS:.0f}s."
        ) from exc
    except httpx.HTTPError as exc:
        raise ExplainerError(f"Could not reach Gemini: {type(exc).__name__}.") from exc

    if response.status_code == 429:
        raise ExplainerRateLimited("Gemini rate limit reached. Try again shortly.")
    if response.status_code in (401, 403):
        # Deliberately not echoing the upstream body: it can quote the key.
        raise ExplainerError(f"Gemini rejected the API key (HTTP {response.status_code}).")
    if response.status_code >= 400:
        raise ExplainerError(f"Gemini returned HTTP {response.status_code}: {_api_error(response)}")

    try:
        parsed = response.json()
    except ValueError as exc:
        raise ExplainerError("Gemini returned a non-JSON response.") from exc

    return normalise(
        _first_json_part(parsed),
        model=settings.GEMINI_MODEL,
        frame_index=frame_index,
        frames_total=frames_total,
    )


def _api_error(response: httpx.Response) -> str:
    """Google's error message, without the rest of the envelope."""
    try:
        message = (response.json().get("error") or {}).get("message")
    except ValueError:
        message = None
    return str(message or "no message")[:300]
