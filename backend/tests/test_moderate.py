"""POST /api/moderate — modes, the five values per block, and tier colouring."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import FakeModels, make_gif, make_png, unit_vector, vector_with_cosine


def post_check(client: TestClient, headers: dict, mode: str, data: bytes, name: str = "a.png"):
    return client.post(
        "/api/moderate",
        headers=headers,
        files={"file": (name, data, "image/png")},
        data={"mode": mode},
    )


def test_nsfw_mode_returns_five_values_and_skips_embedding(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    headers = auth()
    fake_models.nsfw_score = 0.03

    response = post_check(client, headers, "nsfw", make_png())
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["check_type"] == "nsfw"
    assert body["similarity"] is None
    nsfw = body["nsfw"]
    assert set(nsfw) == {
        "nsfw_score",
        "safe_score",
        "tier",
        "threshold",
        "frames_analyzed",
        "frame_count",
        "color",
    }
    assert nsfw["nsfw_score"] == 0.03
    assert nsfw["safe_score"] == 0.97
    assert nsfw["tier"] == "safe"
    assert nsfw["color"] == "green"
    assert nsfw["threshold"] == 0.70
    assert body["overall_tier"] == "safe"
    assert body["overall_color"] == "green"
    # NSFW-only checks never load CLIP.
    assert fake_models.embed_calls == 0


def test_similarity_mode_skips_the_classifier(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    response = post_check(client, auth(), "similarity", make_png())
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["nsfw"] is None
    similarity = body["similarity"]
    assert set(similarity) == {"top_score", "tier", "match_count", "match", "color"}
    # Nothing stored yet, so the first upload is unique with no original.
    assert similarity["top_score"] is None
    assert similarity["tier"] == "Unique"
    assert similarity["match_count"] == 0
    assert similarity["match"] is None
    assert body["overall_tier"] == "safe"
    assert fake_models.classify_calls == 0


def test_both_mode_runs_each_check_once(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    body = post_check(client, auth(), "both", make_png()).json()
    assert body["check_type"] == "both"
    assert body["nsfw"] is not None and body["similarity"] is not None
    assert fake_models.classify_calls == 1 and fake_models.embed_calls == 1


def test_explicit_score_colours_the_card_red(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    fake_models.nsfw_score = 0.94
    nsfw = post_check(client, auth(), "nsfw", make_png()).json()["nsfw"]
    assert (nsfw["tier"], nsfw["color"]) == ("explicit", "red")


def test_borderline_score_colours_the_card_amber(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    fake_models.nsfw_score = 0.55
    body = post_check(client, auth(), "nsfw", make_png()).json()
    assert body["nsfw"]["tier"] == "suggestive"
    assert body["overall_color"] == "amber"


def test_reupload_is_flagged_identical_with_the_original_uploader(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    first_headers = auth("original")
    second_headers = auth("copycat")
    fake_models.vectors = [unit_vector(7), unit_vector(7)]

    first = post_check(client, first_headers, "similarity", make_png(), "original.png").json()
    second = post_check(client, second_headers, "similarity", make_png(), "copy.png").json()

    similarity = second["similarity"]
    assert similarity["tier"] == "Identical"
    assert similarity["top_score"] > 0.99
    assert similarity["match_count"] == 1
    assert similarity["color"] == "red"
    # A duplicate is a red verdict even though the picture itself is safe.
    assert second["overall_tier"] == "explicit"

    match = similarity["match"]
    assert match["check_id"] == first["check_id"]
    assert match["uploaded_by"] == "original"
    assert match["filename"] == "original.png"
    assert match["created_at"]
    assert match["thumbnail_url"] == f"/api/checks/{first['check_id']}/thumbnail"


def test_mid_range_match_is_amber_and_below_the_floor_is_unique(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    headers = auth()
    fake_models.vectors = [
        unit_vector(3),
        vector_with_cosine(3, 4, 0.85),  # -> "Similar"
        vector_with_cosine(3, 5, 0.30),  # -> below the 0.60 floor
    ]
    post_check(client, headers, "similarity", make_png())

    similar = post_check(client, headers, "similarity", make_png()).json()["similarity"]
    assert similar["tier"] == "Similar"
    assert similar["color"] == "amber"
    assert similar["match"] is not None

    unrelated = post_check(client, headers, "similarity", make_png()).json()["similarity"]
    assert unrelated["tier"] == "Unique"
    assert unrelated["color"] == "green"
    # Below the floor there is no "original" to name.
    assert unrelated["match"] is None
    assert unrelated["match_count"] == 0


def test_worst_of_both_wins(client: TestClient, auth, fake_models: FakeModels) -> None:
    headers = auth()
    fake_models.nsfw_score = 0.01  # green on its own
    fake_models.vectors = [unit_vector(9), unit_vector(9)]

    post_check(client, headers, "both", make_png())
    body = post_check(client, headers, "both", make_png()).json()

    assert body["nsfw"]["tier"] == "safe"
    assert body["similarity"]["tier"] == "Identical"
    assert body["overall_tier"] == "explicit"
    assert body["overall_color"] == "red"


def test_gif_reports_sampled_and_total_frames(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    gif = make_gif([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)])
    body = client.post(
        "/api/moderate",
        headers=auth(),
        files={"file": ("clip.gif", gif, "image/gif")},
        data={"mode": "nsfw"},
    ).json()

    assert body["content_type"] == "image/gif"  # sniffed from bytes, not the header
    assert body["nsfw"]["frame_count"] == 4
    assert body["nsfw"]["frames_analyzed"] == 4


def test_rejects_junk_and_bad_modes(client: TestClient, auth, fake_models: FakeModels) -> None:
    headers = auth()
    junk = client.post(
        "/api/moderate",
        headers=headers,
        files={"file": ("notes.txt", b"this is not an image", "text/plain")},
        data={"mode": "nsfw"},
    )
    assert junk.status_code == 415

    bad_mode = post_check(client, headers, "everything", make_png())
    assert bad_mode.status_code == 422


def test_oversize_upload_is_refused(
    client: TestClient, auth, fake_models: FakeModels, monkeypatch
) -> None:
    from app.config import settings

    # Below the ~67-byte floor of any valid PNG, so this is deterministic.
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 10)
    response = post_check(client, auth(), "nsfw", make_png())
    assert response.status_code == 413
