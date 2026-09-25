"""Run the golden set through the LangGraph agent under one or more configurations.

    python evals/run.py --config baseline                 # full golden set
    python evals/run.py --config ab_mini ab_no_rerank     # A/B arms
    python evals/run.py --config temp_0 temp_07 --category evidence   # hyperparameter sweep
    python evals/run.py --config baseline --langsmith     # also log an experiment in LangSmith
    python evals/run.py --smoke                           # 10 cheap examples (CI)

Determinism: evals run against a freshly seeded demo DB (data/eval.db), never the user's real data,
and the semantic cache is disabled so every example hits the full pipeline.
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["DB_PATH"] = str(ROOT / "data" / "eval.db")  # before importing app
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evals"))

from langchain_core.callbacks import AsyncCallbackHandler  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

import evaluators as EV  # noqa: E402
from app.agent import tools as agent_tools  # noqa: E402
from app.agent.graph import compile_graph, initial_input  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.ingest.seed_demo import seed  # noqa: E402
from app.llm import cost_usd  # noqa: E402

S = get_settings()
CONFIGS: dict[str, dict] = {
    "baseline": {"claim_check": False},                        # round-1 reference: PRIMARY_MODEL, rerank, T=0.3, prompt v2, judge v1
    "ab_mini": {"model": S.fast_model, "claim_check": False},                        # A/B 1: cheaper generator
    "ab_no_rerank": {"rerank": False, "claim_check": False},                         # A/B 2: dense retrieval only
    "ab_single_query": {"multi_query": False, "claim_check": False},                 # A/B 3: no triage sub-queries
    "final": {},                                               # current app defaults (judge v2, multi-query, fixes of 09-25)
    "final_repeat": {},                                        # identical to final → run-to-run noise estimate
    "baseline_repeat": {"claim_check": False},                 # identical to baseline → run-to-run noise estimate
    "claim_check": {"claim_check": True},                      # citation judge v2 (per-claim) — now the app default
    "prompt_v1": {"prompt_version": "v1", "citation_check": False, "max_rewrites": 0},  # prompt evolution
    "no_citation_loop": {"citation_check": False, "max_rewrites": 0},                   # value of the loop
    "temp_0": {"temperature": 0.0, "claim_check": False},
    "temp_07": {"temperature": 0.7, "claim_check": False},
    "top_p_05": {"top_p": 0.5, "claim_check": False},
}
SMOKE_IDS = ["ev01", "ev04", "da01", "da03", "rf01", "rf04", "nm02", "adv01", "adv03", "go01"]


class CostTracker(AsyncCallbackHandler):
    def __init__(self):
        self.cost, self.tokens, self.calls = 0.0, 0, 0

    async def on_chat_model_start(self, *args, **kwargs):  # required for chat models; nothing to record
        pass

    async def on_llm_end(self, response, **kwargs):
        for gens in response.generations:
            for g in gens:
                msg = getattr(g, "message", None)
                um = getattr(msg, "usage_metadata", None) or {}
                model = (getattr(msg, "response_metadata", {}) or {}).get("model_name", "")
                if um:
                    self.calls += 1
                    self.tokens += um.get("total_tokens", 0)
                    self.cost += cost_usd(model, um.get("input_tokens", 0), um.get("output_tokens", 0))


def load_golden(categories: list[str] | None, ids: list[str] | None, limit: int | None) -> list[dict]:
    rows = [json.loads(line) for line in open(ROOT / "evals" / "golden.jsonl", encoding="utf-8")]
    if categories:
        rows = [r for r in rows if r["category"] in categories]
    if ids:
        rows = [r for r in rows if r["id"] in ids]
    return rows[:limit] if limit else rows


async def run_example(graph, ex: dict, options: dict, config_name: str) -> dict:
    cb = CostTracker()
    cfg = {"configurable": {"thread_id": f"{config_name}-{ex['id']}"}, "callbacks": [cb],
           "tags": ["eval", config_name, ex["category"]], "run_name": f"eval:{ex['id']}",
           "metadata": {"example_id": ex["id"], "config": config_name, **options}}
    t0 = time.perf_counter()
    try:
        state = await graph.ainvoke(initial_input(ex["question"], ex["persona"], {**options, "use_cache": False}), cfg)
        snap = await graph.aget_state(cfg)
        state = snap.values or state
        error = None
    except Exception as exc:  # noqa: BLE001
        state, error = {}, repr(exc)
    latency = time.perf_counter() - t0
    return {
        "answer": state.get("answer", ""), "route": state.get("route"),
        "evidence": [{"ref": e["ref"], "text": e["text"], "pmcid": e["pmcid"]} for e in state.get("evidence") or []],
        "evidence_pmcids": [e["pmcid"] for e in state.get("evidence") or []],
        "data_context": state.get("data_context"), "citations": state.get("citations"),
        "goal_proposal": state.get("goal_proposal"), "attempts": state.get("attempts", 0),
        "guard_flags": state.get("guard_flags", []), "skills": state.get("skills", []),
        "latency_s": round(latency, 2), "cost_usd": round(cb.cost, 5), "tokens": cb.tokens, "llm_calls": cb.calls,
        "error": error,
    }


def score(ex: dict, out: dict, judges: bool) -> dict:
    ref = {k: v for k, v in ex.items() if k not in ("question", "persona")}
    scores = {}
    for fn in EV.DETERMINISTIC + (EV.JUDGES if judges else []):
        try:
            r = fn({"question": ex["question"]}, out, ref)
        except Exception as exc:  # noqa: BLE001
            r = {"key": fn.__name__, "score": None, "comment": f"evaluator error: {exc}"}
        scores[r["key"]] = {"score": r["score"], "comment": r.get("comment", "")}
    return scores


def aggregate(results: list[dict]) -> dict:
    metrics: dict[str, list[float]] = {}
    for r in results:
        for k, v in r["scores"].items():
            if v["score"] is not None:
                metrics.setdefault(k, []).append(v["score"])
    agg = {k: {"mean": round(statistics.mean(v), 3), "n": len(v)} for k, v in metrics.items()}
    lat = [r["outputs"]["latency_s"] for r in results if r["outputs"]["route"] == "answer"]
    cost = [r["outputs"]["cost_usd"] for r in results]
    agg["latency_p50_s"] = round(statistics.median(lat), 2) if lat else None
    agg["latency_p95_s"] = round(sorted(lat)[max(0, int(len(lat) * 0.95) - 1)], 2) if lat else None
    agg["cost_per_query_usd"] = round(statistics.mean(cost), 5) if cost else None
    agg["rewrite_rate"] = round(sum(1 for r in results if r["outputs"]["attempts"] > 1) / max(1, len(results)), 3)
    agg["errors"] = sum(1 for r in results if r["outputs"]["error"])
    return agg


async def run_config(name: str, rows: list[dict], concurrency: int, judges: bool) -> dict:
    options = CONFIGS[name]
    graph = compile_graph(checkpointer=InMemorySaver())
    sem = asyncio.Semaphore(concurrency)

    async def one(ex):
        async with sem:
            out = await run_example(graph, ex, options, name)
            sc = await asyncio.to_thread(score, ex, out, judges)
            mark = "✓" if sc["route_correct"]["score"] else "✗"
            print(f"  [{name}] {ex['id']:6} {mark} route={out['route']!s:<10} {out['latency_s']:>5}s ${out['cost_usd']:.4f}"
                  + (f"  ERROR {out['error'][:120]}" if out["error"] else ""), flush=True)
            return {"id": ex["id"], "category": ex["category"], "question": ex["question"], "outputs": out, "scores": sc}

    results = await asyncio.gather(*(one(ex) for ex in rows))
    report = {"config": name, "options": options, "models": {"primary": S.primary_model, "fast": S.fast_model},
              "judge_model": EV.JUDGE_MODEL or S.primary_model, "ran_at": datetime.now().isoformat(timespec="seconds"),
              "n": len(results), "aggregate": aggregate(results), "results": results}
    out_dir = ROOT / "evals" / "results"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"{name}.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return report


async def run_langsmith(name: str, rows: list[dict], concurrency: int) -> None:
    """Log the same run as a LangSmith experiment (dataset 'bloom-golden')."""
    from langsmith import Client, aevaluate

    client = Client()
    ds_name = "bloom-golden"
    if not client.has_dataset(dataset_name=ds_name):
        ds = client.create_dataset(ds_name, description="Bloom health-coach golden set (see evals/golden.jsonl)")
        client.create_examples(
            dataset_id=ds.id,
            inputs=[{"question": r["question"], "persona": r["persona"]} for r in rows],
            outputs=[{k: v for k, v in r.items() if k not in ("question", "persona")} for r in rows],
            metadata=[{"id": r["id"], "category": r["category"]} for r in rows],
        )
    graph = compile_graph(checkpointer=InMemorySaver())
    options = CONFIGS[name]

    async def target(inputs: dict) -> dict:
        ex = {"id": f"ls-{abs(hash(inputs['question'])) % 10**8}", "category": "", **inputs}
        return await run_example(graph, ex, options, name)

    await aevaluate(target, data=ds_name, evaluators=EV.ALL, experiment_prefix=f"bloom-{name}",
                    metadata={"config": name, **options, "primary_model": S.primary_model}, max_concurrency=concurrency)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", nargs="+", default=["baseline"], choices=list(CONFIGS))
    ap.add_argument("--category", nargs="*")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--no-judges", action="store_true", help="deterministic metrics only (cheap)")
    ap.add_argument("--smoke", action="store_true", help="10-example CI subset, deterministic metrics only")
    ap.add_argument("--langsmith", action="store_true", help="also log a LangSmith experiment")
    ap.add_argument("--judge-model", default=None)
    ap.add_argument("--min-route-acc", type=float, default=None, help="exit 1 if route accuracy is below this (CI gate)")
    a = ap.parse_args()

    if not S.has_openai:
        sys.exit("OPENAI_API_KEY missing — add it to .env")
    EV.JUDGE_MODEL = a.judge_model
    seed()  # deterministic demo DB for ground truth
    agent_tools._tools, agent_tools._source = agent_tools._local_tools(), "in-process"  # evals don't need the MCP sidecar
    rows = load_golden(a.category, SMOKE_IDS if a.smoke else a.ids, a.limit)
    print(f"{len(rows)} examples × {len(a.config)} config(s)")
    exit_code = 0
    for name in a.config:
        rep = asyncio.run(run_config(name, rows, a.concurrency, judges=not (a.no_judges or a.smoke)))
        print(f"\n== {name} ==")
        for k, v in rep["aggregate"].items():
            print(f"  {k:22} {v}")
        if a.min_route_acc is not None and rep["aggregate"]["route_correct"]["mean"] < a.min_route_acc:
            print(f"  ✗ route accuracy below gate {a.min_route_acc}")
            exit_code = 1
        if a.langsmith:
            asyncio.run(run_langsmith(name, rows, a.concurrency))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
