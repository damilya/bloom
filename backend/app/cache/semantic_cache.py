"""Semantic cache for *general-knowledge* answers.

Key = (persona, question embedding). Hit when cosine ≥ 0.95 and entry is < 7 days old.
Only answers that did NOT use personal data are cached: "is fasted cardio OK with PCOS?" is
reusable, "how's my protein this week?" is not (data changes daily). Stored in SQLite + numpy —
the cache holds at most a few hundred entries, so brute-force cosine is < 1 ms and needs no extra
service.
"""
import json
from datetime import datetime, timedelta

import numpy as np

from app.data import db

THRESHOLD = 0.95
TTL_DAYS = 7

SCHEMA = """CREATE TABLE IF NOT EXISTS semantic_cache (
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, persona TEXT NOT NULL, question TEXT NOT NULL,
  vector BLOB NOT NULL, answer TEXT NOT NULL, citations TEXT NOT NULL, hits INTEGER DEFAULT 0)"""


def _init():
    with db.connect() as c:
        c.execute(SCHEMA)


def lookup(persona: str, vector: list[float]) -> dict | None:
    _init()
    since = (datetime.now() - timedelta(days=TTL_DAYS)).isoformat()
    rows = db.rows("SELECT id, question, vector, answer, citations FROM semantic_cache WHERE persona=? AND ts>=?", (persona, since))
    if not rows:
        return None
    q = np.asarray(vector, dtype=np.float32)
    q /= np.linalg.norm(q) or 1
    mat = np.stack([np.frombuffer(r["vector"], dtype=np.float32) for r in rows])
    mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    sims = mat @ q
    i = int(np.argmax(sims))
    if sims[i] < THRESHOLD:
        return None
    with db.connect() as c:
        c.execute("UPDATE semantic_cache SET hits=hits+1 WHERE id=?", (rows[i]["id"],))
    return {"answer": rows[i]["answer"], "citations": json.loads(rows[i]["citations"]),
            "similarity": round(float(sims[i]), 4), "cached_question": rows[i]["question"]}


def store(persona: str, question: str, vector: list[float], answer: str, citations: list[dict]) -> None:
    _init()
    with db.connect() as c:
        c.execute(
            "INSERT INTO semantic_cache(ts, persona, question, vector, answer, citations) VALUES(?,?,?,?,?,?)",
            (datetime.now().isoformat(), persona, question, np.asarray(vector, dtype=np.float32).tobytes(),
             answer, json.dumps(citations)),
        )


def stats() -> dict:
    _init()
    r = db.rows("SELECT COUNT(*) n, COALESCE(SUM(hits),0) hits FROM semantic_cache")[0]
    return {"entries": r["n"], "hits": r["hits"]}
