"""Test fixtures.

The suite runs against a real SQLite file and a real (temporary) Chroma
collection, so the cosine-distance maths and the SQL writes are genuinely
exercised. Only the two neural models are faked — downloading ~1 GB of weights
is not something a unit test should do.
"""

from __future__ import annotations

import io
import os
import tempfile

import pytest

# Must be set before `app.config` is imported, since Settings is a module-level
# singleton and the engine is built from it at import time.
_TMP = tempfile.mkdtemp(prefix="sentinal-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["CHROMA_PERSIST_DIR"] = f"{_TMP}/chroma"
os.environ["JWT_SECRET"] = "test-only-secret-long-enough-for-hmac-sha256"
os.environ["NSFW_EXPLICIT_THRESHOLD"] = "0.70"
os.environ["NSFW_SUGGESTIVE_THRESHOLD"] = "0.40"
# Empty on purpose, and set here rather than left to chance: it overrides any key
# in backend/.env, so no test can ever reach the real Gemini API. Tests that
# exercise the explainer stub the HTTP call or the service outright.
os.environ["GEMINI_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import classifier, embedder, tiers, vector_store  # noqa: E402

EMBEDDING_DIM = embedder.EMBEDDING_DIM


# --------------------------------------------------------------------------- #
# Sample media
# --------------------------------------------------------------------------- #
def make_png(color: tuple[int, int, int] = (120, 30, 200), size: tuple[int, int] = (64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def make_gif(colors: list[tuple[int, int, int]], size: tuple[int, int] = (48, 48)) -> bytes:
    frames = [Image.new("RGB", size, c) for c in colors]
    buffer = io.BytesIO()
    frames[0].save(
        buffer, format="GIF", save_all=True, append_images=frames[1:], duration=80, loop=0
    )
    return buffer.getvalue()


def unit_vector(index: int) -> list[float]:
    """A one-hot 512-dim vector: two different indices are exactly orthogonal."""
    vector = [0.0] * EMBEDDING_DIM
    vector[index % EMBEDDING_DIM] = 1.0
    return vector


def vector_with_cosine(base_index: int, spare_index: int, cosine: float) -> list[float]:
    """Unit vector whose cosine against `unit_vector(base_index)` is exactly `cosine`.

    Lets a test aim a similarity score straight at the band it wants to check.
    """
    import math

    vector = [0.0] * EMBEDDING_DIM
    vector[base_index % EMBEDDING_DIM] = cosine
    vector[spare_index % EMBEDDING_DIM] = math.sqrt(max(0.0, 1.0 - cosine**2))
    return vector


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeModels:
    """Controls what the stubbed classifier and embedder return."""

    def __init__(self) -> None:
        self.nsfw_score = 0.02
        self.vectors: list[list[float]] = []
        self.embed_calls = 0
        self.classify_calls = 0

    def next_vector(self) -> list[float]:
        self.embed_calls += 1
        if self.vectors:
            return self.vectors.pop(0)
        return unit_vector(self.embed_calls + 100)


@pytest.fixture
def fake_models(monkeypatch: pytest.MonkeyPatch) -> FakeModels:
    fakes = FakeModels()

    def fake_classify(frames, frame_count=None):
        fakes.classify_calls += 1
        score = fakes.nsfw_score
        return classifier.NsfwResult(
            nsfw_score=score,
            safe_score=1.0 - score,
            tier=tiers.classify_nsfw_tier(score),
            threshold=0.70,
            frames_analyzed=len(frames),
            frame_count=frame_count if frame_count is not None else len(frames),
        )

    monkeypatch.setattr(classifier, "classify", fake_classify)
    monkeypatch.setattr(embedder, "embed", lambda frames: fakes.next_vector())
    return fakes


@pytest.fixture(autouse=True)
def clean_state():
    """Fresh tables and a fresh Chroma collection for every test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    vector_store.reset()
    yield


@pytest.fixture
def client(clean_state) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth(client: TestClient):
    """Register a user and return a `(headers, username)` helper factory."""

    def _register(username: str = "tester", password: str = "correct-horse-battery") -> dict:
        response = client.post(
            "/api/auth/register", json={"username": username, "password": password}
        )
        assert response.status_code == 201, response.text
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _register
