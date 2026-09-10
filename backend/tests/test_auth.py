"""Registration, login, and token handling."""

from __future__ import annotations

from fastapi.testclient import TestClient

GOOD = {"username": "alice", "password": "correct-horse-battery"}


def test_register_returns_token_and_user(client: TestClient) -> None:
    response = client.post("/api/auth/register", json=GOOD)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] > 0
    assert body["user"]["username"] == "alice"
    assert "password" not in response.text and "password_hash" not in response.text


def test_duplicate_username_conflicts(client: TestClient) -> None:
    assert client.post("/api/auth/register", json=GOOD).status_code == 201
    assert client.post("/api/auth/register", json=GOOD).status_code == 409


def test_weak_password_rejected(client: TestClient) -> None:
    response = client.post("/api/auth/register", json={"username": "bob", "password": "short"})
    assert response.status_code == 422


def test_username_charset_enforced(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register", json={"username": "not a name!", "password": GOOD["password"]}
    )
    assert response.status_code == 422


def test_long_passphrase_still_verifies(client: TestClient) -> None:
    """Guards the SHA-256 pre-hash: bcrypt alone truncates at 72 bytes."""
    long_password = "x" * 200
    base = {"username": "carol", "password": long_password}
    assert client.post("/api/auth/register", json=base).status_code == 201
    assert client.post("/api/auth/login", json=base).status_code == 200
    # A password sharing the first 72 bytes must not be accepted.
    wrong = {"username": "carol", "password": "x" * 100 + "different"}
    assert client.post("/api/auth/login", json=wrong).status_code == 401


def test_login_flow(client: TestClient) -> None:
    client.post("/api/auth/register", json=GOOD)

    assert client.post("/api/auth/login", json=GOOD).status_code == 200
    # Username lookup is case-insensitive; the password is not.
    assert (
        client.post(
            "/api/auth/login", json={"username": "ALICE", "password": GOOD["password"]}
        ).status_code
        == 200
    )
    assert (
        client.post("/api/auth/login", json={"username": "alice", "password": "nope"}).status_code
        == 401
    )
    assert (
        client.post("/api/auth/login", json={"username": "ghost", "password": "nope"}).status_code
        == 401
    )


def test_me_requires_a_valid_token(client: TestClient) -> None:
    token = client.post("/api/auth/register", json=GOOD).json()["access_token"]

    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_protected_endpoints_reject_anonymous(client: TestClient) -> None:
    for method, path in [
        ("get", "/api/history"),
        ("get", "/api/models"),
        ("get", "/api/checks/1"),
        ("get", "/api/checks/1/image"),
        ("get", "/api/checks/1/thumbnail"),
    ]:
        assert getattr(client, method)(path).status_code == 401, path
    assert client.post("/api/moderate", files={"file": ("a.png", b"x", "image/png")}).status_code == 401


def test_health_and_docs_stay_public(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert client.get("/openapi.json").status_code == 200
