"""Two-stage retrieval: dense recall (Qdrant, top-20) → cross-encoder rerank (FlashRank, top-5).

FlashRank (ms-marco-MiniLM-L-12-v2, ONNX, ~34 MB, CPU) was chosen over Cohere/LLM rerankers:
no extra API key, ~100 ms on CPU, fits in the Docker image. Whether it is worth it is measured
by A/B experiment #2 (see EVALS.md).
"""
import os
from functools import lru_cache

from langsmith import traceable

from app.config import get_settings
from app.llm import get_embeddings
from app.rag import store


@lru_cache
def _ranker():
    from flashrank import Ranker

    cache = get_settings().abs_path(os.environ.get("FLASHRANK_CACHE", "data/models"))
    cache.mkdir(parents=True, exist_ok=True)
    return Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir=str(cache))


@traceable(run_type="retriever", name="research_retriever")
def retrieve(query: str, k: int = 5, fetch_k: int = 20, rerank: bool = True,
             sub_queries: list[str] | None = None, per_paper: int = 3) -> list[dict]:
    """Multi-query retrieval.

    Compound questions ("fasted cardio + women + PCOS") embed close to the dominant topic only, so the
    triage LLM also emits 1–3 focused sub-queries. Each query recalls its own candidates (main: fetch_k,
    facets: fetch_k/2), the cross-encoder re-ranks each list against its own query, and the final list is
    taken round-robin across queries, so a passage answering a minor facet isn't drowned by the dominant
    one. (v1 re-scored the whole pool against every query: same quality, 15 s instead of ~4 s on CPU.)
    A per-paper cap keeps the evidence diverse.
    """
    queries = [query] + [q for q in (sub_queries or []) if q and q.strip().lower() != query.strip().lower()][:3]
    vecs = get_embeddings().embed_documents(queries)
    pool: dict[str, dict] = {}
    order: list[list[str]] = []
    scores: dict[str, float] = {}
    for qi, (q, vec) in enumerate(zip(queries, vecs, strict=True)):
        # main question recalls fetch_k; each facet query recalls half — bounds cross-encoder work (~50 pairs total)
        limit = (fetch_k if qi == 0 else max(5, fetch_k // 2)) if rerank else k
        hits = store.search(vec, limit=limit)
        for h in hits:
            pool.setdefault(h["id"], h)
        ids = [h["id"] for h in hits]
        if rerank and hits:
            from flashrank import RerankRequest

            passages = [{"id": i, "text": f"{h['title']}. {h['section']}. {h['text']}"} for i, h in enumerate(hits)]
            ranked_q = _ranker().rerank(RerankRequest(query=q, passages=passages))
            ids = [hits[r["id"]]["id"] for r in ranked_q]
            for r in ranked_q:
                cid = hits[r["id"]]["id"]
                scores[cid] = max(scores.get(cid, 0.0), round(float(r["score"]), 4))
        order.append(ids)
    if not pool:
        return []
    # round-robin across queries → every facet of a compound question is represented
    ranked, seen = [], set()
    for rank in range(max(len(o) for o in order)):
        for o in order:
            if rank < len(o) and o[rank] not in seen:
                seen.add(o[rank])
                ranked.append(o[rank])
    out, per = [], {}
    for cid in ranked:
        c = pool[cid]
        if per.get(c["pmcid"], 0) >= per_paper:
            continue
        per[c["pmcid"]] = per.get(c["pmcid"], 0) + 1
        out.append({**c, **({"rerank_score": scores[cid]} if cid in scores else {})})
        if len(out) == k:
            break
    return out
