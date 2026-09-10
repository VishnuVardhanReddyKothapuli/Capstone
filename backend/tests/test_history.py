"""History, pagination, blob streaming, and cross-account access rules."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import FakeModels, make_png, unit_vector


def post_check(client: TestClient, headers: dict, mode: str, name: str = "a.png"):
    return client.post(
        "/api/moderate",
        headers=headers,
        files={"file": (name, make_png(), "image/png")},
        data={"mode": mode},
    )


def test_history_is_newest_first_and_paginates(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    headers = auth()
    for index in range(5):
        assert post_check(client, headers, "nsfw", f"file{index}.png").status_code == 200

    page = client.get("/api/history", headers=headers).json()
    assert page["total"] == 5
    assert [item["filename"] for item in page["items"]] == [
        "file4.png",
        "file3.png",
        "file2.png",
        "file1.png",
        "file0.png",
    ]

    second = client.get("/api/history?limit=2&offset=2", headers=headers).json()
    assert second["limit"] == 2 and second["offset"] == 2
    assert [item["filename"] for item in second["items"]] == ["file2.png", "file1.png"]


def test_history_filters_by_check_type(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    headers = auth()
    post_check(client, headers, "nsfw", "one.png")
    post_check(client, headers, "similarity", "two.png")
    post_check(client, headers, "both", "three.png")

    for mode, expected in [("nsfw", "one.png"), ("similarity", "two.png"), ("both", "three.png")]:
        page = client.get(f"/api/history?check_type={mode}", headers=headers).json()
        assert page["total"] == 1
        assert page["items"][0]["filename"] == expected

    assert client.get("/api/history?check_type=bogus", headers=headers).status_code == 422


def test_history_rows_carry_urls_not_blobs(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    headers = auth()
    check_id = post_check(client, headers, "both").json()["check_id"]

    response = client.get("/api/history", headers=headers)
    item = response.json()["items"][0]
    assert item["thumbnail_url"] == f"/api/checks/{check_id}/thumbnail"
    assert item["image_url"] == f"/api/checks/{check_id}/image"
    # The row is the same shape the result card renders, minus any bytes.
    assert set(item) >= {"nsfw", "similarity", "overall_tier", "overall_color", "uploaded_by"}
    assert "image_blob" not in response.text and "thumbnail_blob" not in response.text


def test_history_is_scoped_to_the_owner(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    mine = auth("mine")
    theirs = auth("theirs")
    post_check(client, mine, "nsfw", "mine.png")

    assert client.get("/api/history", headers=mine).json()["total"] == 1
    assert client.get("/api/history", headers=theirs).json()["total"] == 0


def test_blob_endpoints_stream_real_bytes(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    headers = auth()
    check_id = post_check(client, headers, "nsfw").json()["check_id"]

    thumbnail = client.get(f"/api/checks/{check_id}/thumbnail", headers=headers)
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/jpeg"
    assert thumbnail.content.startswith(b"\xff\xd8\xff")  # JPEG SOI

    image = client.get(f"/api/checks/{check_id}/image", headers=headers)
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content == make_png()

    assert client.get("/api/checks/9999/thumbnail", headers=headers).status_code == 404


def test_thumbnails_cross_accounts_but_originals_do_not(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    """A similarity match must be able to show the other account's thumbnail."""
    owner = auth("owner")
    other = auth("other")
    check_id = post_check(client, owner, "similarity").json()["check_id"]

    assert client.get(f"/api/checks/{check_id}/thumbnail", headers=other).status_code == 200
    assert client.get(f"/api/checks/{check_id}/image", headers=other).status_code == 403
    # The verdict JSON of someone else's check is not readable either.
    assert client.get(f"/api/checks/{check_id}", headers=other).status_code == 404


def test_single_check_matches_the_moderate_response(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    headers = auth()
    fake_models.vectors = [unit_vector(2), unit_vector(2)]
    post_check(client, headers, "both", "first.png")
    created = post_check(client, headers, "both", "second.png").json()

    fetched = client.get(f"/api/checks/{created['check_id']}", headers=headers).json()
    assert fetched == created


def test_models_endpoint_reports_live_config(
    client: TestClient, auth, fake_models: FakeModels
) -> None:
    headers = auth()
    post_check(client, headers, "similarity")

    info = client.get("/api/models", headers=headers).json()
    assert info["nsfw_model"] == "Falconsai/nsfw_image_detection"
    assert info["nsfw_labels"] == ["normal", "nsfw"]
    assert info["embedding_model"] == "openai/clip-vit-base-patch32"
    assert info["embedding_dim"] == 512
    assert info["vector_store"].startswith("ChromaDB")
    assert info["vector_store_count"] == 1
    assert info["relational_store"].startswith("SQLite")
    assert info["backend"] == "FastAPI"
    assert info["similarity_bands"]["match_floor"] == 0.60
    # DATABASE_URL can hold a password; only the dialect may be exposed.
    assert "sqlite:///" not in str(info)
