"""API tests: dashboard endpoints and the SSE chat contract (step / final / interrupt events) with fake LLMs."""
import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent import graph as G
from app.agent import tools as T
from app.config import get_settings
from app.data import db
from tests.test_graph import BASE, EVIDENCE, FakeEmb, FakeLLM, FakeStructured, FakeToolLLM


def _events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        ev = next((ln[6:].strip() for ln in block.split("\n") if ln.startswith("event:")), None)
        data = "\n".join(ln[5:].strip() for ln in block.split("\n") if ln.startswith("data:"))
        if ev and data:
            out.append((ev, json.loads(data)))
    return out


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "db_path", lambda: str(tmp_path / "t.db"))
    s = get_settings()
    monkeypatch.setattr(s, "openai_api_key", "sk-test")
    monkeypatch.setattr(s, "db_path", str(tmp_path / "t.db"))
    real_abs = s.abs_path
    monkeypatch.setattr(type(s), "abs_path", lambda self, p: tmp_path / "cp.db" if p.endswith("checkpoints.db") else real_abs(p))
    db.init_db()
    from app.ingest.seed_demo import seed
    seed()
    T._tools, T._source = T._local_tools(), "in-process-test"
    monkeypatch.setattr(main.queries, "weather", lambda *a, **k: {"days": []})
    with TestClient(main.app) as c:
        yield c


def _fake(monkeypatch, scenario):
    monkeypatch.setattr(G, "get_structured", lambda schema, **kw: FakeStructured(schema, scenario))
    monkeypatch.setattr(G, "get_llm", lambda *a, **kw: FakeLLM(scenario))
    monkeypatch.setattr(G, "get_tool_llm", lambda *a, **kw: FakeToolLLM())
    monkeypatch.setattr(G, "get_embeddings", lambda: FakeEmb())
    monkeypatch.setattr(G, "rag_retrieve", lambda *a, **kw: EVIDENCE)


def test_dashboard(client):
    d = client.get("/api/dashboard?days=30").json()
    assert d["cycle"]["known"] and d["trends"]["weight_kg"]["points"] and d["phase_bands"]
    assert client.get("/api/personas").json()[0]["id"] == "coach"


def test_chat_stream_answer(client, monkeypatch):
    _fake(monkeypatch, {"triage": BASE, "judge": [True], "drafts": ["Performance may dip slightly [1]."]})
    r = client.post("/api/chat", json={"message": "Does my cycle affect lifting?", "persona": "coach", "thread_id": "a1"})
    ev = _events(r.text)
    kinds = [e for e, _ in ev]
    assert "step" in kinds and kinds[-1] == "final"
    final = ev[-1][1]
    assert final["route"] == "answer" and final["citations"][0]["n"] == 1


def test_chat_goal_interrupt_then_resume(client, monkeypatch):
    _fake(monkeypatch, {"triage": {**BASE, "intent": "goal"}, "judge": [True], "drafts": ["Plan [1]."]})
    ev = _events(client.post("/api/chat", json={"message": "Set me a goal", "persona": "coach", "thread_id": "g1"}).text)
    assert any(e == "interrupt" and d["goal"]["metric"] == "body_fat_pct" for e, d in ev)
    ev2 = _events(client.post("/api/chat/resume", json={"thread_id": "g1", "decision": "approve"}).text)
    assert ev2[-1][1]["goal_result"]["saved"] is True
    assert client.get("/api/goals").json()[0]["title"] == "Body fat 26 % by Dec"


def test_withings_callback_answers_dashboard_probe(client):
    assert client.head("/withings/callback").status_code == 200
    assert client.get("/withings/callback").status_code == 200


def test_upload_json_rejects_bad_archives(client, tmp_path):
    r = client.post("/api/upload/json", files={"file": ("x.zip", b"not a zip", "application/zip")})
    assert r.status_code == 400 and "ZIP" in r.json()["detail"]
    r = client.post("/api/upload/json", files={"file": ("x.csv", b"a,b", "text/csv")})
    assert r.status_code == 400
