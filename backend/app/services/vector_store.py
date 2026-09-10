"""ChromaDB wrapper — the only place CLIP embeddings are stored or searched.

Replaces the "keep a JSON vector in every SQL row and cosine it in Python"
approach: that was O(rows) per check, this is an HNSW index.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from app.config import settings

_client: Any = None
_collection: Any = None
_load_lock = threading.Lock()


@dataclass(frozen=True)
class Neighbour:
    """One stored image that came back from a similarity query."""

    check_id: int
    score: float  # cosine similarity in [0, 1]; higher means more alike
    metadata: dict[str, Any]


def get_collection() -> Any:
    """Lazily open the persistent client and the single embeddings collection."""
    global _client, _collection
    if _collection is not None:
        return _collection
    with _load_lock:
        if _collection is None:
            import chromadb

            _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
            name = settings.CHROMA_COLLECTION
            # Cosine space, spelled two ways across chromadb versions.
            try:
                _collection = _client.get_or_create_collection(
                    name=name, configuration={"hnsw": {"space": "cosine"}}
                )
            except TypeError:
                _collection = _client.get_or_create_collection(
                    name=name, metadata={"hnsw:space": "cosine"}
                )
    return _collection


def count(user_id: int | None = None) -> int:
    collection = get_collection()
    if user_id is None:
        return int(collection.count())
    return len(collection.get(where={"user_id": user_id}, include=[]).get("ids", []))


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Chroma only accepts str/int/float/bool values."""
    out: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        out[key] = value if isinstance(value, (str, int, float, bool)) else str(value)
    return out


def add(check_id: int, embedding: list[float], metadata: dict[str, Any]) -> None:
    get_collection().add(
        ids=[str(check_id)],
        embeddings=[embedding],
        metadatas=[_clean_metadata({**metadata, "check_id": check_id})],
    )


def query(
    embedding: list[float], top_k: int | None = None, user_id: int | None = None
) -> list[Neighbour]:
    """Nearest stored images, best first.

    Call this *before* `add()` for the current upload, otherwise the new vector
    is its own top match at similarity 1.0.
    """
    collection = get_collection()
    stored = count(user_id)
    if stored == 0:
        return []

    k = settings.SIMILARITY_TOP_K if top_k is None else top_k
    result = collection.query(
        query_embeddings=[embedding],
        n_results=min(k, stored),
        include=["metadatas", "distances"],
        **({"where": {"user_id": user_id}} if user_id is not None else {}),
    )

    ids = (result.get("ids") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0] or [{}] * len(ids)

    neighbours: list[Neighbour] = []
    for raw_id, distance, metadata in zip(ids, distances, metadatas):
        # Chroma reports cosine *distance* (1 - similarity).
        score = min(max(1.0 - float(distance), 0.0), 1.0)
        try:
            check_id = int((metadata or {}).get("check_id", raw_id))
        except (TypeError, ValueError):
            continue
        neighbours.append(Neighbour(check_id=check_id, score=score, metadata=metadata or {}))

    neighbours.sort(key=lambda n: n.score, reverse=True)
    return neighbours


def delete(check_id: int) -> None:
    get_collection().delete(ids=[str(check_id)])


def reset() -> None:
    """Drop and recreate the collection. Used by tests and the reset CLI."""
    global _collection
    get_collection()
    if _client is not None:
        _client.delete_collection(settings.CHROMA_COLLECTION)
        _collection = None
        get_collection()
