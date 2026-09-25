"""Qdrant vector store.

Two modes:
  • QDRANT_URL set (docker-compose / Qdrant Cloud): a real server, collection persisted there.
  • no URL (local dev): in-memory Qdrant loaded from the index snapshot (data/index/*.jsonl + .npy).
    Embedded on-disk Qdrant takes an exclusive file lock, which would stop the API server and the
    eval runner from using the index at the same time — the snapshot avoids that and costs <1 s
    for our ~1–2k chunks.
"""
import json
import threading

import numpy as np
from qdrant_client import QdrantClient, models

from app.config import get_settings

COLLECTION = "research"
_client: QdrantClient | None = None
_lock = threading.Lock()


def _load_snapshot() -> tuple[list[dict], np.ndarray]:
    from app.rag.index import index_dir

    d = index_dir()
    if not (d / "chunks.jsonl").exists():
        return [], np.zeros((0, 1536), dtype=np.float32)
    chunks = [json.loads(line) for line in open(d / "chunks.jsonl", encoding="utf-8")]
    return chunks, np.load(d / "vectors.npy")


def _populate(client: QdrantClient, force: bool) -> None:
    chunks, vecs = _load_snapshot()
    exists = client.collection_exists(COLLECTION)
    if exists and not force and client.count(COLLECTION).count == len(chunks):
        return
    if not chunks:
        return
    if exists:
        client.delete_collection(COLLECTION)
    client.create_collection(COLLECTION, vectors_config=models.VectorParams(size=vecs.shape[1], distance=models.Distance.COSINE))
    client.upload_points(
        COLLECTION,
        points=[models.PointStruct(id=i, vector=vecs[i].tolist(), payload=c) for i, c in enumerate(chunks)],
        batch_size=256,
    )


def get_client() -> QdrantClient:
    global _client
    with _lock:
        if _client is None:
            s = get_settings()
            _client = QdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key or None) if s.qdrant_url else QdrantClient(":memory:")
            _populate(_client, force=False)
        return _client


def reset_store() -> None:
    """Reload after re-indexing: rebuild the in-memory store, or overwrite the server collection."""
    global _client
    if not get_settings().qdrant_url:
        with _lock:
            _client = None
        get_client()
    else:
        _populate(get_client(), force=True)


def search(vector: list[float], limit: int = 20, pmcids: list[str] | None = None) -> list[dict]:
    client = get_client()
    if not client.collection_exists(COLLECTION):
        return []
    flt = None
    if pmcids:
        flt = models.Filter(must=[models.FieldCondition(key="pmcid", match=models.MatchAny(any=pmcids))])
    res = client.query_points(COLLECTION, query=vector, limit=limit, query_filter=flt, with_payload=True)
    return [{**p.payload, "vector_score": round(p.score, 4)} for p in res.points]
