# LLM and hyperparameter choice

## Constraint
One vendor account (OpenAI) for the course project. Everything goes through LangChain's `ChatOpenAI`,
so swapping vendors is a config change plus one line in `backend/app/llm.py`.

## Role-based model routing

| Role | Model | Calls per query | Why |
|---|---|---|---|
| Final answer, goal proposal | **gpt-4.1** (`PRIMARY_MODEL`) | 1 (+1 per rewrite) | the only text the user reads. Best instruction-following and citation discipline in the non-reasoning family; long context (1M) absorbs Skill + evidence + data comfortably |
| Triage / routing | gpt-4.1-mini (`FAST_MODEL`) | 1 | a classification with a structured schema, where mini is reliable. Safety recall is measured by `route_correct` |
| Tool planning | gpt-4.1-mini | 1 | picks 1–4 tools from 8 well-described ones |
| Citation judge (in-graph) | gpt-4.1-mini | 1 | binary support judgments on short passages |
| Foodvisor vision extraction | gpt-4.1-mini (vision) | per upload | transcription with a strict schema. Errors are caught by Atwater/total checks and user confirmation |
| Embeddings | text-embedding-3-small | 1 | see ARCHITECTURE.md |
| Fallback | gpt-4.1-mini (`FALLBACK_MODEL`) | on error / over budget | same API surface, so it degrades gracefully |

**Why not a reasoning model (o-series / GPT-5 class) for the answer?** (a) The hard part is *grounding*, not multi-step reasoning. The facts come from retrieval and tools. (b) Reasoning models don't expose `temperature` / `top_p`, which the course asks us to tune experimentally. (c) Several seconds of extra latency before the first token hurts a chat UX. This is a hypothesis we'd revisit if faithfulness plateaus.

**Why not a local model?** No GPU on the target machine. Small local models are markedly worse at citation discipline, and the privacy benefit is partly achieved already: raw health data stays in SQLite, and only summaries needed for the question reach the API.

## Cost per query (pre-build estimate; measured values below)

Prices per 1M tokens (input / output), as configured in `app/llm.py` (verify against current OpenAI pricing): gpt-4.1 $2 / $8, gpt-4.1-mini $0.40 / $1.60.

| Step | Model | ~in / out tokens | ~cost |
|---|---|---|---|
| triage | mini | 900 / 80 | $0.0005 |
| tool planning | mini | 1,500 / 80 | $0.0007 |
| generate | 4.1 | 5,000 / 450 | $0.0136 |
| citation judge | mini | 3,000 / 150 | $0.0014 |
| **total** | | | **≈ $0.016** (+ ≈ $0.015 per rewrite) |

**Measured** (EVALS.md, 42 examples): ≈ $0.008 per research answer, ≈ $0.0003 per red-flag/blocked message, mean $0.004–0.005 per query.
gpt-4.1-mini as generator: $0.0024 mean, citation precision −0.04. It's the configured fallback.

Cost controls: role routing (above), semantic cache for general questions, the Skill is loaded only when triggered, tool payloads are compacted (time series down-sampled to ~20 points), a daily budget auto-downgrades the primary model, and `max_tokens` is capped.

## Hyperparameters

| Param | Value | Where it comes from |
|---|---|---|
| `temperature` (generate) | 0.3 | sweep 0 / 0.3 / 0.7 on the evidence subset (EVALS.md §3). Prior: health answers should be stable; a small amount of variety makes the persona voices less robotic |
| `temperature` (triage, judges, tools, vision) | 0 | classification / extraction: we want determinism |
| `top_p` | 1.0 | we tune temperature *or* top_p, not both. The `top_p_05` arm checks that restricting the nucleus doesn't beat temperature tuning |
| `max_tokens` | 900 | prompt targets ≤ 300 words ≈ 400 tokens. 900 is headroom without run-on answers |
| retrieval `k` / `fetch_k` | 5 / 20 | 5 passages ≈ 2.5k tokens of evidence (fits the cost budget); 20 candidates give the reranker room |
| cache threshold | 0.95 cosine | conservative; a false hit on a health question is costly |
| citation rewrites | ≤ 2 | bounds the loop's worst-case latency and cost |

All of these can be overridden per request (`options` in the graph state), which is how the eval harness runs the A/B arms without code changes.
