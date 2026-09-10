"""The Gemini explainer: score repair, error mapping, caching, and scoping.

No test here reaches the network. `conftest` blanks GEMINI_API_KEY so the feature
is off by default, and the tests that need it on stub `httpx.post` outright.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.services import explainer
from tests.conftest import make_png

GOOD = {
    "classification": "safe",
    "confidence": 0.9,
    "scores": {"safe": 0.9, "suggestive": 0.05, "nsfw": 0.03, "violent": 0.01, "hate": 0.01},
    "detectedText": None,
    "textToxicity": 0.0,
    "description": "A plain violet rectangle.",
    "explanation": "No unsafe content is visible, so publishing is allowed.",
}


def normalise(payload: dict[str, Any]) -> explainer.Explanation:
    return explainer.normalise(payload, model="test-model", frame_index=0, frames_total=1)


def envelope(payload: dict[str, Any], finish: str = "STOP") -> dict[str, Any]:
    """The shape generateContent actually returns."""
    return {
        "candidates": [
            {"content": {"parts": [{"text": json.dumps(payload)}]}, "finishReason": finish}
        ]
    }


class Recorder:
    """Stands in for httpx.post and remembers every call."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"url": url, **kwargs})
        outcome = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def gemini(monkeypatch: pytest.MonkeyPatch):
    """Returns an installer that switches the feature on with a stubbed transport.

    Nothing happens until it is called, so a test can also observe the off state.
    """

    def install(*outcomes: Any) -> Recorder:
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-not-a-real-one")
        recorder = Recorder(list(outcomes) or [httpx.Response(200, json=envelope(GOOD))])
        monkeypatch.setattr(httpx, "post", recorder)
        return recorder

    return install


def upload(client: TestClient, headers: dict, mode: str = "both") -> dict:
    response = client.post(
        "/api/moderate",
        headers=headers,
        files={"file": ("sample.png", make_png(), "image/png")},
        data={"mode": mode},
    )
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# normalise(): the prompt's own score rules, enforced server-side
# --------------------------------------------------------------------------- #
def test_a_consistent_answer_is_left_alone() -> None:
    result = normalise(GOOD)

    assert result.classification == "safe"
    assert result.confidence == pytest.approx(0.9)
    assert result.publish_allowed is True
    assert result.repaired is False
    assert sum(result.scores.values()) == pytest.approx(1.0, abs=1e-3)
    assert result.detected_text is None


def test_scores_that_do_not_total_one_are_rescaled() -> None:
    payload = {**GOOD, "scores": {"safe": 4.0, "suggestive": 0.0, "nsfw": 1.0, "violent": 0.0, "hate": 0.0}}

    result = normalise(payload)

    assert sum(result.scores.values()) == pytest.approx(1.0)
    assert result.scores["safe"] == pytest.approx(0.8)
    assert result.confidence == pytest.approx(0.8)
    assert result.repaired is True


def test_percentages_survive_normalisation() -> None:
    """A model that answers 90/5/3/1/1 must not collapse to a flat distribution.

    This is why the per-score helper has no upper clamp: clamping to 1 before
    summing would turn every value above 1 into the same number.
    """
    payload = {
        **GOOD,
        "confidence": 90,
        "scores": {"safe": 90, "suggestive": 5, "nsfw": 3, "violent": 1, "hate": 1},
    }

    result = normalise(payload)

    assert result.scores["safe"] == pytest.approx(0.9)
    assert result.scores["suggestive"] == pytest.approx(0.05)
    assert result.classification == "safe"


@pytest.mark.parametrize(
    ("stated", "top", "expected"),
    [
        # The model said safe but its own numbers point at nsfw: rule 6 says the
        # non-safe category wins.
        ("safe", "nsfw", "nsfw"),
        # And the other way round: a stated nsfw is not softened by a safe argmax.
        ("nsfw", "safe", "nsfw"),
        ("suggestive", "hate", "hate"),
        ("violent", "suggestive", "violent"),
    ],
)
def test_disagreement_resolves_to_the_less_publishable_class(
    stated: str, top: str, expected: str
) -> None:
    scores = {name: 0.05 for name in explainer.CLASSES}
    scores[top] = 0.8

    result = normalise({**GOOD, "classification": stated, "scores": scores})

    assert result.classification == expected
    assert result.confidence == pytest.approx(result.scores[expected])
    assert result.repaired is True


def test_an_unknown_class_falls_back_to_the_argmax() -> None:
    scores = {name: 0.05 for name in explainer.CLASSES}
    scores["violent"] = 0.8

    result = normalise({**GOOD, "classification": "spicy", "scores": scores})

    assert result.classification == "violent"
    assert result.publish_allowed is False
    assert result.repaired is True


def test_all_scores_unusable_is_an_error() -> None:
    payload = {**GOOD, "scores": {name: 0.0 for name in explainer.CLASSES}}

    with pytest.raises(explainer.ExplainerError, match="no usable scores"):
        normalise(payload)


def test_garbage_scores_become_zero() -> None:
    """Strings, nulls, NaN and negatives must not poison the distribution."""
    payload = {
        **GOOD,
        "classification": "nsfw",
        "scores": {
            "safe": "not a number",
            "suggestive": None,
            "nsfw": 0.5,
            "violent": float("nan"),
            "hate": -3.0,
        },
    }

    result = normalise(payload)

    assert result.scores == {
        "safe": 0.0,
        "suggestive": 0.0,
        "nsfw": 1.0,
        "violent": 0.0,
        "hate": 0.0,
    }
    assert result.classification == "nsfw"


def test_a_missing_scores_object_is_an_error() -> None:
    with pytest.raises(explainer.ExplainerError):
        normalise({"classification": "safe", "confidence": 1.0})


def test_text_toxicity_is_clamped_not_rescaled() -> None:
    assert normalise({**GOOD, "textToxicity": 7.0}).text_toxicity == 1.0
    assert normalise({**GOOD, "textToxicity": -1.0}).text_toxicity == 0.0
    assert normalise({**GOOD, "textToxicity": "0.4"}).text_toxicity == pytest.approx(0.4)


def test_a_wrong_confidence_is_recomputed_and_flagged() -> None:
    result = normalise({**GOOD, "confidence": 0.1})

    assert result.confidence == pytest.approx(0.9)
    assert result.repaired is True


@pytest.mark.parametrize("value", [None, "", "   ", "null", "NULL", "none", "No text", "n/a"])
def test_empty_detected_text_becomes_none(value: str | None) -> None:
    assert normalise({**GOOD, "detectedText": value}).detected_text is None


def test_real_detected_text_is_kept() -> None:
    assert normalise({**GOOD, "detectedText": " BUY NOW "}).detected_text == "BUY NOW"


def test_long_free_text_is_truncated() -> None:
    payload = {
        **GOOD,
        "detectedText": "x" * (explainer.MAX_TEXT + 500),
        "description": "d" * (explainer.MAX_PROSE + 500),
        "explanation": "e" * (explainer.MAX_PROSE + 500),
    }

    result = normalise(payload)

    assert len(result.detected_text or "") == explainer.MAX_TEXT
    assert len(result.description) == explainer.MAX_PROSE
    assert len(result.explanation) == explainer.MAX_PROSE


@pytest.mark.parametrize("name", ["suggestive", "nsfw", "violent", "hate"])
def test_only_safe_may_publish(name: str) -> None:
    scores = {other: 0.05 for other in explainer.CLASSES}
    scores[name] = 0.8

    result = normalise({**GOOD, "classification": name, "scores": scores})

    assert result.publish_allowed is False
    assert normalise(GOOD).publish_allowed is True


# --------------------------------------------------------------------------- #
# POST /api/checks/{id}/explain
# --------------------------------------------------------------------------- #
def test_without_a_key_the_endpoint_says_so(client: TestClient, auth, fake_models) -> None:
    headers = auth()
    check_id = upload(client, headers)["check_id"]

    response = client.post(f"/api/checks/{check_id}/explain", headers=headers)

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_anonymous_callers_are_rejected(client: TestClient) -> None:
    assert client.post("/api/checks/1/explain").status_code == 401


def test_unknown_and_other_peoples_checks_are_both_404(
    client: TestClient, auth, fake_models, gemini
) -> None:
    gemini()
    owner = auth("owner")
    stranger = auth("stranger")
    check_id = upload(client, owner)["check_id"]

    assert client.post("/api/checks/99999/explain", headers=owner).status_code == 404
    # Same answer for a check that exists but belongs to someone else, so the
    # response cannot be used to enumerate other accounts' uploads.
    assert client.post(f"/api/checks/{check_id}/explain", headers=stranger).status_code == 404


@pytest.mark.parametrize("mode", ["nsfw", "similarity", "both"])
def test_every_mode_can_be_explained(
    client: TestClient, auth, fake_models, gemini, mode: str
) -> None:
    """The box is offered on all three kinds of check, not just the NSFW one."""
    gemini()
    headers = auth()
    check_id = upload(client, headers, mode)["check_id"]

    body = client.post(f"/api/checks/{check_id}/explain", headers=headers).json()

    assert body["check_type"] == mode
    assert body["explanation"]["classification"] == "safe"


def test_a_successful_call_stores_the_whole_block(
    client: TestClient, auth, fake_models, gemini
) -> None:
    recorder = gemini()
    headers = auth()
    check_id = upload(client, headers)["check_id"]

    response = client.post(f"/api/checks/{check_id}/explain", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()

    explanation = body["explanation"]
    assert set(explanation) == {
        "classification",
        "confidence",
        "scores",
        "detected_text",
        "text_toxicity",
        "description",
        "explanation",
        "publish_allowed",
        "model",
        "frame_index",
        "frames_total",
        "repaired",
    }
    assert explanation["classification"] == "safe"
    assert explanation["publish_allowed"] is True
    assert explanation["model"] == settings.GEMINI_MODEL
    assert explanation["frames_total"] == 1
    assert explanation["explanation"].startswith("No unsafe content")
    assert body["explained_at"] is not None
    assert len(recorder.calls) == 1


def test_the_request_sent_to_gemini_is_the_agreed_contract(
    client: TestClient, auth, fake_models, gemini
) -> None:
    recorder = gemini()
    headers = auth()
    check_id = upload(client, headers)["check_id"]
    client.post(f"/api/checks/{check_id}/explain", headers=headers)

    call = recorder.calls[0]
    assert call["url"].endswith(f"/models/{settings.GEMINI_MODEL}:generateContent")
    # The key travels in a header; a key in the query string ends up in logs.
    assert call["headers"]["x-goog-api-key"] == settings.GEMINI_API_KEY
    assert settings.GEMINI_API_KEY not in call["url"]

    sent = call["json"]
    assert sent["systemInstruction"]["parts"][0]["text"] == explainer.PROMPT
    inline = sent["contents"][0]["parts"][0]["inline_data"]
    assert inline["mime_type"] == "image/jpeg"
    assert inline["data"]  # base64 of the downscaled frame
    config = sent["generationConfig"]
    assert config["temperature"] == 0.0
    assert config["responseMimeType"] == "application/json"
    assert config["responseSchema"] == explainer.RESPONSE_SCHEMA
    # This is the moderation tool; Gemini's own filters must not pre-empt it.
    assert all(rule["threshold"] == "BLOCK_NONE" for rule in sent["safetySettings"])


def test_the_answer_is_cached_and_refresh_overrides_it(
    client: TestClient, auth, fake_models, gemini
) -> None:
    other = {**GOOD, "classification": "violent", "confidence": 0.8,
             "scores": {"safe": 0.1, "suggestive": 0.05, "nsfw": 0.05, "violent": 0.8, "hate": 0.0}}
    recorder = gemini(
        httpx.Response(200, json=envelope(GOOD)), httpx.Response(200, json=envelope(other))
    )
    headers = auth()
    check_id = upload(client, headers)["check_id"]

    first = client.post(f"/api/checks/{check_id}/explain", headers=headers).json()
    second = client.post(f"/api/checks/{check_id}/explain", headers=headers).json()

    assert len(recorder.calls) == 1, "the cached row should be reused"
    assert second["explanation"] == first["explanation"]

    refreshed = client.post(
        f"/api/checks/{check_id}/explain?refresh=true", headers=headers
    ).json()

    assert len(recorder.calls) == 2
    assert refreshed["explanation"]["classification"] == "violent"
    assert refreshed["explanation"]["publish_allowed"] is False


def test_the_explanation_never_moves_the_local_verdict(
    client: TestClient, auth, fake_models, gemini
) -> None:
    """Gemini is a second opinion, not an input to the tier."""
    hostile = {**GOOD, "classification": "hate", "confidence": 1.0,
               "scores": {"safe": 0.0, "suggestive": 0.0, "nsfw": 0.0, "violent": 0.0, "hate": 1.0}}
    gemini(httpx.Response(200, json=envelope(hostile)))
    headers = auth()
    fake_models.nsfw_score = 0.01
    before = upload(client, headers)

    after = client.post(f"/api/checks/{before['check_id']}/explain", headers=headers).json()

    assert after["explanation"]["classification"] == "hate"
    assert after["explanation"]["publish_allowed"] is False
    # The card shows the disagreement instead of resolving it.
    assert after["overall_tier"] == before["overall_tier"] == "safe"
    assert after["overall_color"] == "green"


def test_the_stored_block_surfaces_through_history_and_single_check(
    client: TestClient, auth, fake_models, gemini
) -> None:
    gemini()
    headers = auth()
    check_id = upload(client, headers)["check_id"]
    client.post(f"/api/checks/{check_id}/explain", headers=headers)

    single = client.get(f"/api/checks/{check_id}", headers=headers).json()
    assert single["explanation"]["classification"] == "safe"
    assert single["explained_at"] is not None

    page = client.get("/api/history", headers=headers).json()
    assert page["items"][0]["explanation"]["description"] == GOOD["description"]


def test_an_unexplained_check_reports_no_explanation(
    client: TestClient, auth, fake_models
) -> None:
    headers = auth()
    body = upload(client, headers)

    assert body["explanation"] is None
    assert body["explained_at"] is None


# --------------------------------------------------------------------------- #
# Failure mapping: every upstream problem gets a status a client can act on
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("outcome", "status", "fragment"),
    [
        (httpx.Response(429, json={"error": {"message": "quota"}}), 429, "rate limit"),
        (httpx.TimeoutException("too slow"), 504, "did not answer"),
        (httpx.ConnectError("no route"), 502, "Could not reach Gemini"),
        (httpx.Response(401, json={"error": {"message": "API key not valid"}}), 502, "API key"),
        (httpx.Response(500, json={"error": {"message": "backend error"}}), 502, "backend error"),
        (httpx.Response(200, content=b"not json at all"), 502, "non-JSON"),
        (httpx.Response(200, json={"candidates": []}), 502, "no candidates"),
        (
            httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
            422,
            "declined to analyse",
        ),
        (
            httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": []}, "finishReason": "IMAGE_SAFETY"}]},
            ),
            422,
            "IMAGE_SAFETY",
        ),
        (
            httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]},
            ),
            502,
            "empty answer",
        ),
        (
            httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "[]"}]}}]}),
            502,
            "not an object",
        ),
    ],
)
def test_upstream_failures_map_to_useful_statuses(
    client: TestClient, auth, fake_models, gemini, outcome: Any, status: int, fragment: str
) -> None:
    gemini(outcome)
    headers = auth()
    check_id = upload(client, headers)["check_id"]

    response = client.post(f"/api/checks/{check_id}/explain", headers=headers)

    assert response.status_code == status, response.text
    assert fragment.lower() in response.json()["detail"].lower()
    # A failed explanation leaves the row exactly as it was.
    assert client.get(f"/api/checks/{check_id}", headers=headers).json()["explanation"] is None


def test_a_rejected_key_is_reported_without_echoing_the_upstream_body(
    client: TestClient, auth, fake_models, gemini
) -> None:
    """Google's 401 body can quote the key back, so it is not passed through."""
    recorder = gemini()
    leaky = {"error": {"message": f"API key not valid: {settings.GEMINI_API_KEY}"}}
    recorder.responses[:] = [httpx.Response(403, json=leaky)]
    headers = auth()
    check_id = upload(client, headers)["check_id"]

    detail = client.post(f"/api/checks/{check_id}/explain", headers=headers).json()["detail"]

    assert "403" in detail
    assert settings.GEMINI_API_KEY not in detail


def test_a_fenced_json_answer_is_still_read(
    client: TestClient, auth, fake_models, gemini
) -> None:
    """`responseMimeType` should prevent this, but a code fence is recoverable."""
    fenced = {
        "candidates": [
            {"content": {"parts": [{"text": f"```json\n{json.dumps(GOOD)}\n```"}]},
             "finishReason": "STOP"}
        ]
    }
    gemini(httpx.Response(200, json=fenced))
    headers = auth()
    check_id = upload(client, headers)["check_id"]

    body = client.post(f"/api/checks/{check_id}/explain", headers=headers).json()

    assert body["explanation"]["classification"] == "safe"


# --------------------------------------------------------------------------- #
# The key itself
# --------------------------------------------------------------------------- #
def test_models_endpoint_reports_availability_but_never_the_key(
    client: TestClient, auth, gemini
) -> None:
    headers = auth()

    off = client.get("/api/models", headers=headers).json()
    assert off["explainer_configured"] is False
    assert off["explainer_model"] == settings.GEMINI_MODEL

    gemini()
    on = client.get("/api/models", headers=headers)
    assert on.json()["explainer_configured"] is True
    assert settings.GEMINI_API_KEY not in on.text
