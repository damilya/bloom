"""LangGraph workflow for the coach chat.

 START → input_guard ─blocked→ finalize
            │
         triage ─red flag→ doctor_referral → finalize
            │  ─off-topic / smalltalk→ canned → finalize
            │
      skill_router → cache_lookup ─hit→ finalize
                         │
                    gather_data (MCP tools, if needed)
                         │
                    retrieve (Qdrant → FlashRank, if needed)
                         │
                    generate ◄──────────────┐  (loop: ≤ 2 rewrites)
                         │                  │
                    citation_check ─fail────┘
                         │ pass / out of retries
                    output_guard ─intent=goal→ propose_goal → human_approval (interrupt) → save_goal
                         │                                                                     │
                      finalize ◄───────────────────────────────────────────────────────────────┘
"""
import json
import re
from datetime import date
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from app.agent import prompts
from app.agent.skill import select_skills
from app.agent.tools import load_tools
from app.cache import semantic_cache
from app.config import get_settings
from app.data.queries import METRIC_UNITS
from app.guards.input_guard import REFUSAL, check_input
from app.guards.output_guard import check_output
from app.llm import get_embeddings, get_llm, get_structured, get_tool_llm
from app.rag.retriever import retrieve as rag_retrieve

DEFAULT_OPTIONS = {
    "model": None,            # override generate model (A/B)
    "temperature": None,      # override (hyperparameter sweep)
    "top_p": None,
    "max_tokens": None,
    "rerank": True,           # A/B: reranker on/off
    "k": 5,
    "use_cache": True,
    "prompt_version": "v2",   # v1 | v2
    "max_rewrites": 2,
    "citation_check": True,
    "multi_query": True,      # triage-generated sub-queries for retrieval
    "claim_check": True,      # citation judge v2 (per-claim verdicts): +0.16 citation precision in evals vs holistic v1
}


# ───────────────────────────── state ─────────────────────────────

RESET = "__reset__"


def trace_reducer(old: list[str] | None, new: list[str] | None) -> list[str]:
    """Append step logs; a leading RESET marker starts a fresh log for a new turn."""
    new = new or []
    if new[:1] == [RESET]:
        return new[1:]
    return (old or []) + new


class State(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]  # conversation (persists per thread)
    question: str
    persona: str
    options: dict
    route: str                     # blocked | doctor | off_topic | smalltalk | answer | cached
    guard_in: dict
    triage: dict
    skills: list[str]
    q_vector: list[float] | None
    data_context: dict
    tool_source: str
    evidence: list[dict]
    draft: str
    attempts: int
    citation_feedback: str
    citation_report: dict
    answer: str
    citations: list[dict]
    guard_flags: list[str]
    cache_info: dict | None
    goal_proposal: dict | None
    goal_result: dict | None
    trace: Annotated[list[str], trace_reducer]  # human-readable step log for the UI (reset per turn)


class Triage(BaseModel):
    red_flag: bool = Field(description="needs a clinician rather than coaching")
    red_flag_reason: str | None = Field(None, description="short phrase describing the concern, in second person, e.g. 'chest pain during runs'")
    urgency: Literal["none", "see_doctor", "urgent"] = "none"
    in_domain: bool = True
    intent: Literal["question", "goal", "smalltalk"] = "question"
    needs_personal_data: bool = False
    needs_research: bool = True
    womens_health_topic: bool = False
    search_queries: list[str] = Field(
        default_factory=list,
        description="1–3 short literature-search queries, one per facet of the question; empty if no research is needed",
    )


class CitationCheck(BaseModel):
    all_supported: bool
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_citations: list[str] = Field(default_factory=list)
    feedback: str = ""


class ClaimVerdicts(BaseModel):
    verdicts: list[bool] = Field(description="one entry per numbered CLAIM: does its cited PASSAGE support it?")
    feedback: list[str] = Field(default_factory=list, description="for each unsupported claim: what the passage actually says")


def cited_claims(answer: str) -> list[tuple[str, int]]:
    """(sentence, citation number) pairs; a sentence citing [1][2] yields two pairs."""
    out = []
    for sent in re.split(r"(?<=[.!?])\s+|\n+", answer):
        for n in re.findall(r"\[(\d+)\]", sent):
            out.append((re.sub(r"\[(\d+|data)\]", "", sent).strip(" -*"), int(n)))
    return out


class GoalProposal(BaseModel):
    title: str = Field(description="short goal title, e.g. 'Body fat to 26 % by 15 December'")
    metric: str | None = Field(None, description="tracked metric or null")
    target_value: float | None = None
    unit: str | None = None
    deadline: str | None = Field(None, description="YYYY-MM-DD")
    weekly_plan: list[str] = Field(default_factory=list)
    rationale: str = Field(description="1–2 sentences: why this target/pace is realistic for the user")


def _opts(state: State) -> dict:
    return {**DEFAULT_OPTIONS, **(state.get("options") or {})}


def _history(state: State, n: int = 6) -> list[AnyMessage]:
    msgs = [m for m in state.get("messages", []) if isinstance(m, (HumanMessage, AIMessage))]
    return msgs[:-1][-n:]  # exclude the current question (added separately)


# ───────────────────────────── nodes ─────────────────────────────

def input_guard(state: State) -> dict:
    raw = state["messages"][-1].content if state.get("messages") else state.get("question", "")
    chk = check_input(raw)
    reset = {  # per-turn fields (the checkpointer keeps state across turns)
        "question": chk.text, "guard_in": {"blocked": chk.blocked, "reasons": chk.reasons, "redactions": chk.redactions},
        "evidence": [], "data_context": {}, "draft": "", "attempts": 0, "citation_feedback": "", "citation_report": {},
        "answer": "", "citations": [], "guard_flags": [], "cache_info": None, "goal_proposal": None,
        "goal_result": None, "skills": [], "q_vector": None, "triage": {}, "tool_source": "",
    }
    if chk.blocked:
        return {**reset, "route": "blocked", "answer": REFUSAL, "trace": [RESET, "🛡️ Input guard blocked the message"]}
    note = f" (redacted {', '.join(chk.redactions)})" if chk.redactions else ""
    return {**reset, "route": "answer", "trace": [RESET, f"🛡️ Input checked{note}"]}


def triage(state: State) -> dict:
    llm = get_structured(Triage, role="fast")
    t: Triage = llm.invoke([SystemMessage(prompts.TRIAGE_SYSTEM), *_history(state, 4), HumanMessage(state["question"])])
    route = "answer"
    if t.red_flag:
        route = "doctor"
    elif t.intent == "smalltalk":
        route = "smalltalk"
    elif not t.in_domain:
        route = "off_topic"
    return {"triage": t.model_dump(), "route": route,
            "trace": [f"🩺 Triage: {route}" + (f" — {t.red_flag_reason}" if t.red_flag else "")]}


def doctor_referral(state: State) -> dict:
    t = state["triage"]
    reason = t.get("red_flag_reason") or "this symptom"
    urgent = prompts.URGENT_LINE if t.get("urgency") == "urgent" else ""
    return {"answer": prompts.DOCTOR_REFERRAL.format(reason=reason, urgent_line=urgent),
            "trace": ["🚑 Escalated to doctor referral"]}


def canned(state: State) -> dict:
    if state["route"] == "smalltalk":
        return {"answer": prompts.SMALLTALK.format(user_name=get_settings().user_name)}
    return {"answer": prompts.OFF_TOPIC, "trace": ["↩️ Off-topic, politely declined"]}


def skill_router(state: State) -> dict:
    skills = select_skills(state["question"], llm_flag=state["triage"].get("womens_health_topic", False))
    names = [s.name for s in skills]
    return {"skills": names, "trace": [f"📘 Skill loaded: {', '.join(names)}"] if names else []}


def cache_lookup(state: State) -> dict:
    o, t = _opts(state), state["triage"]
    cacheable = o["use_cache"] and not t.get("needs_personal_data") and t.get("intent") == "question" and not _history(state)
    if not cacheable:
        return {}
    vec = get_embeddings().embed_query(state["question"])
    hit = semantic_cache.lookup(state["persona"], vec)
    if hit:
        return {"route": "cached", "answer": hit["answer"], "citations": hit["citations"],
                "cache_info": {"hit": True, "similarity": hit["similarity"], "cached_question": hit["cached_question"]},
                "trace": [f"⚡ Semantic cache hit (similarity {hit['similarity']})"]}
    return {"q_vector": vec, "cache_info": {"hit": False}}


async def gather_data(state: State) -> dict:
    if not state["triage"].get("needs_personal_data") and state["triage"].get("intent") != "goal":
        return {}
    tools, source = await load_tools()
    read_tools = [t for t in tools if t.name != "save_goal"]
    persona = prompts.PERSONAS[state["persona"]]["name"]
    llm = get_tool_llm(read_tools, role="fast")
    msg = await llm.ainvoke([
        SystemMessage(prompts.TOOLS_SYSTEM.format(persona=persona, today=date.today().isoformat())),
        *_history(state, 4), HumanMessage(state["question"]),
    ])
    calls = list(msg.tool_calls or [])[:4]
    if state["skills"] and not any(c["name"] == "get_cycle_status" for c in calls):
        calls.append({"name": "get_cycle_status", "args": {}, "id": "auto-cycle"})
    by_name = {t.name: t for t in read_tools}
    ctx: dict[str, Any] = {}
    for c in calls:
        tool = by_name.get(c["name"])
        if not tool:
            continue
        try:
            out = await tool.ainvoke(c["args"])
            out = out if isinstance(out, str) else json.dumps(out, default=str)
        except Exception as exc:  # noqa: BLE001
            out = json.dumps({"error": str(exc)})
        key = f"{c['name']}({', '.join(f'{k}={v}' for k, v in c['args'].items())})"
        ctx[key] = _compact(out)
    return {"data_context": ctx, "tool_source": source,
            "trace": [f"📊 Read your data via {source}: {', '.join(k.split('(')[0] for k in ctx)}"] if ctx else []}


def _compact(raw: str, limit: int = 3500) -> Any:
    """Trim long tool payloads (time series) so the prompt stays small: keep summaries, sample points."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return raw[:limit]
    if isinstance(data, dict):
        if isinstance(data.get("points"), list) and len(data["points"]) > 20:
            pts = data["points"]
            data["points"] = pts[:: max(1, len(pts) // 20)] + [pts[-1]]
        if isinstance(data.get("items"), list):
            data["items"] = data["items"][:12]
        if isinstance(data.get("daily"), list) and len(data["daily"]) > 14:
            data["daily"] = data["daily"][-14:]
    s = json.dumps(data, default=str)
    return json.loads(s) if len(s) <= limit else s[:limit]


def retrieve(state: State) -> dict:
    t = state["triage"]
    # Deterministic safety net: general (non-personal-data) questions are always grounded in research, even
    # if the triage LLM said needs_research=false (eval ev09: WHO activity guidelines answered from memory).
    general_question = t.get("intent") == "question" and not t.get("needs_personal_data")
    if not (t.get("needs_research") or state["skills"] or general_question):
        return {"evidence": []}
    o = _opts(state)
    subs = t.get("search_queries") if o.get("multi_query", True) else None
    docs = rag_retrieve(state["question"], k=o["k"], rerank=o["rerank"], sub_queries=subs)
    refs = sorted({d["ref"] for d in docs})
    return {"evidence": docs, "trace": [f"🔎 Retrieved {len(docs)} passages ({'reranked' if o['rerank'] else 'dense only'}): {'; '.join(refs)}"]}


def _evidence_block(evidence: list[dict]) -> str:
    if not evidence:
        return "EVIDENCE: (none retrieved — do not cite any papers)"
    parts = []
    for i, d in enumerate(evidence, 1):
        loc = f"{d['section']}" + (f", p.{d['page']}" if d.get("page") else "")
        parts.append(f"[{i}] {d['ref']} — {d['title']} ({d['level']}; {loc})\n{d['text']}")
    return "EVIDENCE:\n" + "\n\n".join(parts)


def _system_prompt(state: State) -> str:
    o = _opts(state)
    p = prompts.PERSONAS[state["persona"]]
    if o["prompt_version"] == "v1":
        return prompts.GENERATE_V1.format(persona_name=p["name"])
    from app.agent.skill import load_skills

    skill_block = ""
    for name in state.get("skills", []):
        skill_block += f"\n\n<skill name=\"{name}\">\n{load_skills()[name].body}\n</skill>"
    return prompts.GENERATE_V2.format(persona_name=p["name"], focus=p["focus"], voice=p["voice"],
                                      user_name=get_settings().user_name, today=date.today().isoformat(),
                                      skill_block=skill_block)


async def generate(state: State) -> dict:
    o = _opts(state)
    s = get_settings()
    llm = get_llm("primary", model=o["model"],
                  temperature=o["temperature"] if o["temperature"] is not None else s.gen_temperature,
                  top_p=o["top_p"] if o["top_p"] is not None else s.gen_top_p,
                  max_tokens=o["max_tokens"] or s.gen_max_tokens, streaming=True)
    data = json.dumps(state.get("data_context") or {}, default=str)
    context = f"DATA (user's own records, cite as [data]):\n{data}\n\n{_evidence_block(state.get('evidence', []))}"
    msgs: list[AnyMessage] = [SystemMessage(_system_prompt(state)), SystemMessage(context), *_history(state), HumanMessage(state["question"])]
    if state.get("citation_feedback"):
        msgs += [AIMessage(state["draft"]),
                 HumanMessage(f"A fact-checker found problems with your answer:\n{state['citation_feedback']}\n"
                              "Rewrite the full answer fixing them: remove or soften unsupported claims, fix citation numbers. "
                              "Do not mention the fact-checker.")]
    resp = await llm.ainvoke(msgs)
    attempt = state.get("attempts", 0) + 1
    return {"draft": resp.content, "attempts": attempt,
            "trace": ["✍️ Drafted answer" if attempt == 1 else f"✍️ Rewrote answer (attempt {attempt})"]}


def citation_check(state: State) -> dict:
    o = _opts(state)
    draft, evidence = state["draft"], state.get("evidence", [])
    if not o["citation_check"]:
        return {"citation_report": {"skipped": True}, "citation_feedback": ""}
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", draft)}
    invalid = sorted(n for n in cited if n < 1 or n > len(evidence))
    if not evidence:
        if cited:
            return {"citation_report": {"all_supported": False, "invalid": sorted(cited)},
                    "citation_feedback": "You cited papers but no evidence was provided. Remove all [n] citations.",
                    "trace": ["🔍 Citation check: citations without evidence"]}
        return {"citation_report": {"all_supported": True, "no_evidence": True}, "citation_feedback": ""}
    if not cited:
        report = {"all_supported": False, "reason": "no citations"}
        fb = "The answer makes research-based claims but has no [n] citations. Add them where the evidence supports a sentence."
        return {"citation_report": report, "citation_feedback": fb, "trace": ["🔍 Citation check: no citations → rewrite"]}
    if o["claim_check"]:
        return _claim_level_check(draft, evidence, invalid)
    judge = get_structured(CitationCheck, role="fast")
    res: CitationCheck = judge.invoke([SystemMessage(prompts.CITATION_JUDGE),
                                       HumanMessage(f"{_evidence_block(evidence)}\n\nANSWER:\n{draft}")])
    ok = res.all_supported and not invalid
    fb = "" if ok else (res.feedback + (f" Invalid citation numbers: {invalid}." if invalid else ""))
    report = {**res.model_dump(), "invalid": invalid, "all_supported": ok}
    return {"citation_report": report, "citation_feedback": fb,
            "trace": ["🔍 Citations verified ✓" if ok else f"🔍 Citation check failed: {len(res.unsupported_claims) + len(res.missing_citations)} issue(s)"]}


def _claim_level_check(draft: str, evidence: list[dict], invalid: list[int]) -> dict:
    """v2: judge every (sentence, citation) pair against its own passage, in one mini-model call.

    The holistic v1 judge passed answers the offline evaluator scored at 0.78 citation precision:
    one verdict for the whole answer lets 'mostly fine' hide overstated sentences.
    """
    claims = [(c, n) for c, n in cited_claims(draft) if 1 <= n <= len(evidence)]
    listing = "\n".join(f"CLAIM {i}: {c}\nPASSAGE [{n}]: {evidence[n - 1]['text']}" for i, (c, n) in enumerate(claims, 1))
    res: ClaimVerdicts = get_structured(ClaimVerdicts, role="fast").invoke([
        SystemMessage(prompts.CLAIM_JUDGE), HumanMessage(listing)])
    verdicts = (res.verdicts + [True] * len(claims))[: len(claims)]
    bad = [(c, n) for (c, n), ok in zip(claims, verdicts, strict=True) if not ok]
    ok = not bad and not invalid
    fb = ""
    if not ok:
        lines = [f'- "{c[:160]}" is not supported by [{n}]' for c, n in bad]
        lines += [f"- {f}" for f in res.feedback[:6]]
        if invalid:
            lines.append(f"- citation numbers {invalid} do not exist")
        fb = ("These cited sentences overstate or misattribute their sources:\n" + "\n".join(lines) +
              "\nRewrite so each cited sentence says only what its passage says; move general advice out of cited sentences.")
    return {"citation_report": {"all_supported": ok, "claims": len(claims), "unsupported": len(bad), "invalid": invalid},
            "citation_feedback": fb,
            "trace": [f"🔍 Citations verified ✓ ({len(claims)} claims)" if ok else f"🔍 {len(bad)}/{len(claims)} cited claims unsupported"]}


def output_guard(state: State) -> dict:
    evidence = state.get("evidence", [])
    text, flags = check_output(state["draft"], len(evidence))
    report = state.get("citation_report") or {}
    if report and report.get("all_supported") is False and state.get("attempts", 0) > _opts(state)["max_rewrites"]:
        text += "\n\n> ⚠️ Some statements above could not be fully verified against the research I have — treat them as general guidance."
        flags.append("unverified_after_retries")
    used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text) if 1 <= int(n) <= len(evidence)})
    citations = [{"n": n, **{k: evidence[n - 1].get(k) for k in ("ref", "title", "year", "doi", "url", "section", "page", "level", "text", "pmcid")}}
                 for n in used]
    out: dict = {"answer": text, "citations": citations, "guard_flags": flags,
                 "trace": [f"🛡️ Output guard: {', '.join(flags)}"] if flags else []}
    t = state["triage"]
    if (state.get("q_vector") and not flags and t.get("intent") == "question"
            and not state.get("data_context") and _opts(state)["use_cache"]):
        semantic_cache.store(state["persona"], state["question"], state["q_vector"], text, citations)
    return out


def propose_goal(state: State) -> dict:
    p = prompts.PERSONAS[state["persona"]]
    llm = get_structured(GoalProposal, role="primary", temperature=0.2)
    g: GoalProposal = llm.invoke([
        SystemMessage(prompts.GOAL_SYSTEM.format(persona_name=p["name"], today=date.today().isoformat(),
                                                 metrics=", ".join(METRIC_UNITS))),
        SystemMessage(f"DATA:\n{json.dumps(state.get('data_context') or {}, default=str)}"),
        *_history(state), HumanMessage(state["question"]), AIMessage(state.get("answer", "")),
    ])
    goal = g.model_dump()
    if goal.get("metric") not in METRIC_UNITS:
        goal["metric"] = None
    return {"goal_proposal": goal, "trace": ["🎯 Proposed a goal — waiting for your approval"]}


async def human_approval(state: State) -> dict:
    decision = interrupt({"type": "goal_approval", "goal": state["goal_proposal"]})
    # resume payload: {"decision": "approve" | "edit" | "reject", "goal": {...edited...}}
    choice = (decision or {}).get("decision", "reject")
    if choice == "reject":
        return {"goal_result": {"saved": False}, "trace": ["🙅 Goal rejected"],
                "answer": state["answer"] + "\n\nNo problem — I didn't save the goal. We can adjust it any time."}
    goal = {**state["goal_proposal"], **((decision or {}).get("goal") or {})}
    tools, _ = await load_tools()
    save = next(t for t in tools if t.name == "save_goal")
    args = {k: goal.get(k) for k in ("title", "metric", "target_value", "unit", "deadline", "weekly_plan", "rationale")}
    res = await save.ainvoke({k: v for k, v in args.items() if v is not None})
    res = json.loads(res) if isinstance(res, str) else res
    return {"goal_result": {"saved": True, **(res if isinstance(res, dict) else {}), "goal": goal},
            "trace": [f"✅ Goal {'edited and ' if choice == 'edit' else ''}saved"],
            "answer": state["answer"] + f"\n\n✅ Saved your goal **{goal['title']}** — you'll see it on the dashboard."}


def finalize(state: State) -> dict:
    return {"messages": [AIMessage(state.get("answer", ""))]}


# ───────────────────────────── edges ─────────────────────────────

def after_guard(state: State) -> str:
    return "finalize" if state["route"] == "blocked" else "triage"


def after_triage(state: State) -> str:
    return {"doctor": "doctor_referral", "off_topic": "canned", "smalltalk": "canned"}.get(state["route"], "skill_router")


def after_cache(state: State) -> str:
    return "finalize" if state.get("route") == "cached" else "gather_data"


def after_check(state: State) -> str:
    if state.get("citation_feedback") and state.get("attempts", 0) <= _opts(state)["max_rewrites"]:
        return "generate"
    return "output_guard"


def after_output(state: State) -> str:
    return "propose_goal" if state["triage"].get("intent") == "goal" else "finalize"


def build_graph() -> StateGraph:
    g = StateGraph(State)
    for name, fn in [("input_guard", input_guard), ("triage", triage), ("doctor_referral", doctor_referral),
                     ("canned", canned), ("skill_router", skill_router), ("cache_lookup", cache_lookup),
                     ("gather_data", gather_data), ("retrieve", retrieve), ("generate", generate),
                     ("citation_check", citation_check), ("output_guard", output_guard),
                     ("propose_goal", propose_goal), ("human_approval", human_approval), ("finalize", finalize)]:
        g.add_node(name, fn)
    g.add_edge(START, "input_guard")
    g.add_conditional_edges("input_guard", after_guard, ["triage", "finalize"])
    g.add_conditional_edges("triage", after_triage, ["doctor_referral", "canned", "skill_router"])
    g.add_edge("doctor_referral", "finalize")
    g.add_edge("canned", "finalize")
    g.add_edge("skill_router", "cache_lookup")
    g.add_conditional_edges("cache_lookup", after_cache, ["finalize", "gather_data"])
    g.add_edge("gather_data", "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "citation_check")
    g.add_conditional_edges("citation_check", after_check, ["generate", "output_guard"])
    g.add_conditional_edges("output_guard", after_output, ["propose_goal", "finalize"])
    g.add_edge("propose_goal", "human_approval")
    g.add_edge("human_approval", "finalize")
    g.add_edge("finalize", END)
    return g


def compile_graph(checkpointer=None):
    return build_graph().compile(checkpointer=checkpointer)


def initial_input(question: str, persona: str = "coach", options: dict | None = None) -> dict:
    return {"messages": [HumanMessage(question)], "persona": persona, "options": options or {}}
