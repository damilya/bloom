"""LLM factory: role-based model choice, fallback chain, daily budget, cost tracking.

Roles
  primary — user-facing answer + goal proposal (quality matters most)
  fast    — triage, tool planning, citation judge, vision extraction (cheap, low latency)
Fallback: every runnable is wrapped with `.with_fallbacks()` → FALLBACK_MODEL, so an outage /
rate-limit on the primary degrades quality instead of failing the request.
Budget: when today's spend passes DAILY_BUDGET_USD, the primary role is downgraded to the fallback model.
"""
from datetime import date
from typing import Any, Literal

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import get_settings
from app.data import db

Role = Literal["primary", "fast"]

# USD per 1M tokens (input, output) — update when pricing changes
PRICING = {
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
}


def cost_usd(model: str, inp: int, out: int) -> float:
    key = next((k for k in sorted(PRICING, key=len, reverse=True) if model.startswith(k)), None)
    if not key:
        return 0.0
    pi, po = PRICING[key]
    return (inp * pi + out * po) / 1_000_000


class UsageTracker(BaseCallbackHandler):
    """Persists token usage + cost of every chat call (feeds the budget guard and the cost-per-query metric)."""

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            for gens in response.generations:
                for g in gens:
                    msg = getattr(g, "message", None)
                    um = getattr(msg, "usage_metadata", None) or {}
                    model = (getattr(msg, "response_metadata", {}) or {}).get("model_name", "")
                    if um:
                        inp, out = um.get("input_tokens", 0), um.get("output_tokens", 0)
                        with db.connect() as conn:
                            conn.execute(
                                "INSERT INTO llm_usage(model, input_tokens, output_tokens, cost_usd) VALUES(?,?,?,?)",
                                (model, inp, out, cost_usd(model, inp, out)),
                            )
        except Exception:
            pass  # accounting must never break a user request


_tracker = UsageTracker()


def spent_today() -> float:
    r = db.rows("SELECT COALESCE(SUM(cost_usd),0) s FROM llm_usage WHERE substr(ts,1,10)=?", (date.today().isoformat(),))
    return float(r[0]["s"])


def model_for(role: Role) -> str:
    s = get_settings()
    if role == "fast":
        return s.fast_model
    if spent_today() >= s.daily_budget_usd:
        return s.fallback_model  # budget guard
    return s.primary_model


def _chat(model: str, **kw) -> ChatOpenAI:
    s = get_settings()
    return ChatOpenAI(
        model=model, api_key=s.openai_api_key or "missing", timeout=60, max_retries=2,
        callbacks=[_tracker], stream_usage=True, **{k: v for k, v in kw.items() if v is not None},
    )


def get_llm(role: Role = "primary", *, model: str | None = None, temperature: float | None = None,
            top_p: float | None = None, max_tokens: int | None = None, streaming: bool = False) -> Runnable:
    """Chat model with automatic fallback. Explicit `model` overrides the role (used by A/B evals)."""
    s = get_settings()
    name = model or model_for(role)
    kw = dict(temperature=temperature, top_p=top_p, max_tokens=max_tokens, streaming=streaming or None)
    main = _chat(name, **kw)
    if name == s.fallback_model:
        return main
    return main.with_fallbacks([_chat(s.fallback_model, **kw)])


def get_structured(schema: type, role: Role = "fast", *, model: str | None = None, temperature: float = 0.0) -> Runnable:
    """Structured-output runnable (Pydantic schema) with fallback."""
    s = get_settings()
    name = model or model_for(role)
    main = _chat(name, temperature=temperature).with_structured_output(schema)
    if name == s.fallback_model:
        return main
    return main.with_fallbacks([_chat(s.fallback_model, temperature=temperature).with_structured_output(schema)])


def get_tool_llm(tools: list, role: Role = "fast") -> Runnable:
    s = get_settings()
    name = model_for(role)
    main = _chat(name, temperature=0).bind_tools(tools)
    if name == s.fallback_model:
        return main
    return main.with_fallbacks([_chat(s.fallback_model, temperature=0).bind_tools(tools)])


def get_embeddings() -> OpenAIEmbeddings:
    s = get_settings()
    return OpenAIEmbeddings(model=s.embedding_model, api_key=s.openai_api_key or "missing")
