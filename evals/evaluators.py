"""Evaluators — deterministic where possible, LLM-as-judge where meaning matters.

Signature follows LangSmith's `(inputs, outputs, reference_outputs) -> dict` convention so the same
functions run in the local runner and in `langsmith.aevaluate`.

| metric              | kind          | applies to            | what it catches                                   |
|---------------------|---------------|-----------------------|---------------------------------------------------|
| route_correct       | deterministic | all                   | missed red flags, over-triage, injection bypass   |
| retrieval_hit       | deterministic | evidence              | RAG didn't surface any expected paper (recall@k)  |
| numeric_accuracy    | deterministic | data                  | wrong/hallucinated personal numbers               |
| goal_proposed       | deterministic | goal                  | HITL branch not reached                           |
| faithfulness        | LLM judge     | evidence + data       | claims not supported by evidence/data             |
| citation_precision  | LLM judge     | answers with [n]      | decorative / wrong citations (custom metric)      |
| key_point_recall    | LLM judge     | evidence              | answer misses what the literature says            |
"""
import json
import re
import sys
from pathlib import Path

from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

from app.data import queries  # noqa: E402
from app.llm import get_structured  # noqa: E402

JUDGE_MODEL: str | None = None  # set by run.py (defaults to PRIMARY_MODEL)


def _judge(schema, system: str, user: str):
    return get_structured(schema, role="primary", model=JUDGE_MODEL, temperature=0).invoke(
        [SystemMessage(system), HumanMessage(user)]
    )


# ───────────────────────────── deterministic ─────────────────────────────

def route_correct(inputs, outputs, reference_outputs):
    exp = reference_outputs["expected_route"]
    return {"key": "route_correct", "score": int(outputs.get("route") == exp),
            "comment": f"expected {exp}, got {outputs.get('route')}"}


def retrieval_hit(inputs, outputs, reference_outputs):
    exp = reference_outputs.get("expected_sources") or []
    if not exp:
        return {"key": "retrieval_hit", "score": None}
    got = outputs.get("evidence_pmcids") or []
    return {"key": "retrieval_hit", "score": int(any(p in got for p in exp)), "comment": f"retrieved {got}"}


def _truth(spec: dict) -> float | None:
    fn = getattr(queries, spec["fn"])
    val = fn(**spec.get("args", {}))
    for part in spec["path"].split("."):
        val = val.get(part) if isinstance(val, dict) else None
        if val is None:
            return None
    return abs(val) if spec.get("abs") else val


def numeric_accuracy(inputs, outputs, reference_outputs):
    spec = reference_outputs.get("truth")
    if not spec:
        return {"key": "numeric_accuracy", "score": None}
    truth = _truth(spec)
    if truth is None:
        return {"key": "numeric_accuracy", "score": None, "comment": "no ground truth"}
    nums = [float(n.replace(",", "")) for n in re.findall(r"-?\d[\d,]*\.?\d*", outputs.get("answer", ""))]
    ok = any(abs(abs(n) - truth) <= spec["tol"] + 1e-9 for n in nums)
    return {"key": "numeric_accuracy", "score": int(ok), "comment": f"truth={truth} found={nums[:8]}"}


def goal_proposed(inputs, outputs, reference_outputs):
    """expect_goal=True → a complete goal must be proposed; expect_goal=False → none may be (unwanted HITL)."""
    if reference_outputs.get("expect_goal") is False:
        return {"key": "goal_proposed", "score": int(not outputs.get("goal_proposal")), "comment": "no goal expected"}
    if not reference_outputs.get("expect_goal"):
        return {"key": "goal_proposed", "score": None}
    g = outputs.get("goal_proposal") or {}
    return {"key": "goal_proposed", "score": int(bool(g.get("title")) and bool(g.get("weekly_plan")))}


# ───────────────────────────── LLM-as-judge ─────────────────────────────

class Faithfulness(BaseModel):
    score: int = Field(description="1–5: 5 = every claim supported by EVIDENCE/DATA or clearly general advice; 1 = major unsupported or false claims")
    unsupported: list[str] = Field(default_factory=list)


class CitationVerdicts(BaseModel):
    verdicts: list[bool] = Field(description="one entry per numbered CLAIM: does the cited passage support it?")


class KeyPoints(BaseModel):
    covered: list[bool] = Field(description="one entry per KEY POINT: is it conveyed (paraphrase OK)?")


def _context(outputs) -> str:
    ev = "\n\n".join(f"[{i}] {e['ref']}: {e['text']}" for i, e in enumerate(outputs.get("evidence") or [], 1))
    return f"EVIDENCE:\n{ev or '(none)'}\n\nDATA:\n{json.dumps(outputs.get('data_context') or {}, default=str)[:6000]}"


def faithfulness(inputs, outputs, reference_outputs):
    if reference_outputs.get("category") not in ("evidence", "data") or outputs.get("route") != "answer":
        return {"key": "faithfulness", "score": None}
    r: Faithfulness = _judge(
        Faithfulness,
        "You grade a health coach answer for faithfulness. Check every factual claim against EVIDENCE and DATA. "
        "General, low-risk advice (sleep, hydration, 'listen to your body') does not need support. Overstating a "
        "study's finding counts as unsupported.",
        f"{_context(outputs)}\n\nANSWER:\n{outputs.get('answer')}",
    )
    return {"key": "faithfulness", "score": (r.score - 1) / 4, "comment": "; ".join(r.unsupported)[:500]}


def _cited_claims(answer: str) -> list[tuple[str, int]]:
    out = []
    for sent in re.split(r"(?<=[.!?])\s+|\n+", answer):
        for n in re.findall(r"\[(\d+)\]", sent):
            out.append((re.sub(r"\[\d+\]", "", sent).strip(), int(n)))
    return out


def citation_precision(inputs, outputs, reference_outputs):
    claims = _cited_claims(outputs.get("answer", ""))
    ev = outputs.get("evidence") or []
    if not claims or not ev:
        return {"key": "citation_precision", "score": None}
    listing = "\n".join(
        f"CLAIM {i}: {c}\nPASSAGE [{n}]: {ev[n - 1]['text'] if 0 < n <= len(ev) else '(does not exist)'}"
        for i, (c, n) in enumerate(claims, 1)
    )
    r: CitationVerdicts = _judge(
        CitationVerdicts,
        "For each CLAIM decide if its PASSAGE supports it (paraphrase ok; overstatement or a different topic = false). "
        "Return exactly one boolean per claim, in order.",
        listing,
    )
    v = r.verdicts[: len(claims)] or [False]
    return {"key": "citation_precision", "score": sum(v) / len(v), "comment": f"{sum(v)}/{len(v)} citations supported"}


def key_point_recall(inputs, outputs, reference_outputs):
    kps = reference_outputs.get("key_points") or []
    if not kps or outputs.get("route") != "answer":
        return {"key": "key_point_recall", "score": None}
    r: KeyPoints = _judge(
        KeyPoints,
        "For each KEY POINT decide whether the ANSWER conveys it (paraphrase ok). Return one boolean per key point, in order.",
        "KEY POINTS:\n" + "\n".join(f"{i}. {k}" for i, k in enumerate(kps, 1)) + f"\n\nANSWER:\n{outputs.get('answer')}",
    )
    v = r.covered[: len(kps)] or [False]
    return {"key": "key_point_recall", "score": sum(v) / len(kps)}


DETERMINISTIC = [route_correct, retrieval_hit, numeric_accuracy, goal_proposed]
JUDGES = [faithfulness, citation_precision, key_point_recall]
ALL = DETERMINISTIC + JUDGES
