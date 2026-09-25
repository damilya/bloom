"""FastAPI backend: dashboard API, ingestion endpoints, Withings OAuth, and the streaming chat (SSE)."""
import json
import logging
import shutil
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.agent.graph import compile_graph, initial_input
from app.agent.prompts import PERSONAS
from app.agent.tools import load_tools
from app.cache import semantic_cache
from app.config import get_settings
from app.data import db, queries
from app.ingest import apple_health, foodvisor_vision, tanita_kinetix, withings
from app.llm import spent_today

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")
JOBS: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    cp_path = get_settings().abs_path("data/checkpoints.db")
    async with AsyncSqliteSaver.from_conn_string(str(cp_path)) as saver:
        app.state.graph = compile_graph(checkpointer=saver)
        try:
            _, source = await load_tools()
            log.info("agent tools loaded via %s", source)
        except Exception as exc:  # noqa: BLE001
            log.warning("tool preload failed: %s", exc)
        yield


app = FastAPI(title="Cycle-Aware Health Coach", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[get_settings().frontend_origin, "http://localhost:3000"],
                   allow_methods=["*"], allow_headers=["*"])


def uploads_dir() -> Path:
    d = get_settings().abs_path("data/uploads")
    d.mkdir(parents=True, exist_ok=True)
    return d


# ───────────────────────────── status & dashboard ─────────────────────────────

@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/status")
def status():
    s = get_settings()
    index = s.abs_path("data/index/chunks.jsonl")
    counts = {t: db.rows(f"SELECT COUNT(*) n FROM {t}")[0]["n"] for t in ("measurements", "workouts", "cycle_days", "meals", "goals")}
    import os
    return {
        "openai": s.has_openai, "withings": withings.status(), "research_index": index.exists(),
        "langsmith": os.environ.get("LANGSMITH_TRACING", "false").lower() == "true",
        "data": counts, "spent_today_usd": round(spent_today(), 4), "budget_usd": s.daily_budget_usd,
        "cache": semantic_cache.stats(), "models": {"primary": s.primary_model, "fast": s.fast_model, "fallback": s.fallback_model},
    }


@app.get("/api/dashboard")
def dashboard(days: int = 90):
    start = (date.today() - timedelta(days=days)).isoformat()
    trends = {m: queries.body_composition_trend(m, days) for m in ("weight_kg", "body_fat_pct", "muscle_mass_kg")}
    vitals = {m: queries.body_composition_trend(m, min(days, 60)) for m in ("resting_hr", "sleep_hours", "hrv_ms", "steps")}
    try:
        wx = queries.weather(date.today().isoformat(), (date.today() + timedelta(days=4)).isoformat())
    except Exception:  # noqa: BLE001
        wx = {"days": []}
    return {
        "user": get_settings().user_name, "today": date.today().isoformat(),
        "latest": queries.latest_metrics(), "cycle": queries.cycle_status(),
        "phase_bands": queries.cycle_phase_bands(start, date.today().isoformat()),
        "trends": trends, "vitals": vitals, "nutrition": queries.nutrition_summary(14),
        "workouts": queries.workouts(days), "goals": queries.list_goals(), "weather": wx,
    }


@app.get("/api/trend")
def trend(metric: str = "weight_kg", days: int = 90, source: str | None = None):
    return queries.body_composition_trend(metric, days, source)


@app.get("/api/nutrition")
def nutrition(days: int = 30):
    return queries.nutrition_summary(max(1, min(days, 365)))


@app.get("/api/meals")
def meals(day: str | None = None):
    return queries.meals_on(day or date.today().isoformat())


@app.get("/api/personas")
def personas():
    return [{"id": k, **v} for k, v in PERSONAS.items()]


# ───────────────────────────── goals ─────────────────────────────

@app.get("/api/goals")
def goals(status: str | None = "active"):
    return queries.list_goals(status)


class GoalStatus(BaseModel):
    status: str


@app.patch("/api/goals/{goal_id}")
def patch_goal(goal_id: int, body: GoalStatus):
    queries.update_goal_status(goal_id, body.status)
    return {"ok": True}


# ───────────────────────────── ingestion ─────────────────────────────

@app.post("/api/demo/seed")
def seed_demo():
    from app.ingest.seed_demo import seed

    return seed()


def _run_job(job_id: str, fn, *args):
    JOBS[job_id] = {"status": "running"}
    try:
        JOBS[job_id] = {"status": "done", "result": fn(*args)}
    except Exception as exc:  # noqa: BLE001
        log.exception("job failed")
        JOBS[job_id] = {"status": "error", "error": str(exc)}


@app.post("/api/upload/apple-health")
async def upload_apple(bg: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".zip", ".xml")):
        raise HTTPException(400, "Upload export.zip or export.xml from the Health app")
    dest = uploads_dir() / f"apple_{uuid.uuid4().hex[:8]}{Path(file.filename).suffix}"
    with open(dest, "wb") as fh:
        shutil.copyfileobj(file.file, fh)
    job = uuid.uuid4().hex[:10]
    JOBS[job] = {"status": "queued"}
    bg.add_task(_run_job, job, apple_health.parse_apple_health, dest)
    return {"job_id": job}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    return JOBS.get(job_id, {"status": "unknown"})


@app.post("/api/upload/json")
async def upload_json(file: UploadFile = File(...), source: str | None = None):
    """Kinetix / Tanita exports: a single .json file or a .zip containing several."""
    name = Path(file.filename or "upload").name
    if not name.lower().endswith((".json", ".zip")):
        raise HTTPException(400, "Upload a .json export or a .zip of .json exports")
    dest = uploads_dir() / f"{uuid.uuid4().hex[:8]}_{name}"
    dest.write_bytes(await file.read())
    if name.lower().endswith(".zip"):
        try:
            result = tanita_kinetix.import_zip(dest)
        except zipfile.BadZipFile as exc:
            raise HTTPException(400, "Not a valid ZIP file") from exc
        if not result["files"]:
            raise HTTPException(400, "The ZIP contains no .json files")
        return result
    try:
        r = tanita_kinetix.import_json(dest, source)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(400, f"Not valid JSON: {exc}") from exc
    return {"files": [r], "measurements": r["measurements"], "workouts": r["workouts"]}


@app.post("/api/upload/foodvisor")
async def upload_foodvisor(file: UploadFile = File(...)):
    if not get_settings().has_openai:
        raise HTTPException(400, "OPENAI_API_KEY is not configured")
    data = await file.read()
    if len(data) > 8_000_000:
        raise HTTPException(400, "Image too large (max 8 MB)")
    mime = file.content_type or "image/png"
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/heic": ".heic"}.get(mime, ".img")
    (uploads_dir() / f"foodvisor_{uuid.uuid4().hex[:8]}{ext}").write_bytes(data)  # kept for audit / re-extraction
    result = foodvisor_vision.extract(data, mime)
    log.info("foodvisor extraction: %d items, unreadable=%s, date=%s", len(result["items"]), result["unreadable"], result["date"])
    return result


class FoodvisorConfirm(BaseModel):
    date: str
    items: list[dict]


@app.post("/api/foodvisor/confirm")
def foodvisor_confirm(body: FoodvisorConfirm):
    return {"saved": foodvisor_vision.save(body.date, body.items)}


@app.post("/api/weather/sync")
def weather_sync(days: int = 120):
    from app.ingest.weather import sync_weather

    return {"days": sync_weather(date.today() - timedelta(days=days), date.today() + timedelta(days=7))}


# ───────────────────────────── Withings OAuth ─────────────────────────────

@app.get("/withings/connect")
def withings_connect():
    try:
        return RedirectResponse(withings.authorize_url())
    except withings.WithingsError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.api_route("/withings/callback", methods=["GET", "HEAD"])
def withings_callback(request: Request, code: str | None = None, state: str | None = None):
    # Withings probes the registered callback URL (HEAD, sometimes a bare GET) when the app is saved in the
    # developer dashboard and refuses anything but HTTP 200 — answer probes before the OAuth logic.
    if request.method == "HEAD" or not code:
        return PlainTextResponse("ok")
    try:
        withings.exchange_code(code, state)
        result = withings.sync()
    except withings.WithingsError as exc:
        return HTMLResponse(f"<h3>Withings connection failed</h3><pre>{exc}</pre>", status_code=400)
    return RedirectResponse(f"{get_settings().frontend_origin}/data?withings=connected&n={result['measurements']}")


@app.get("/api/withings/status")
def withings_status():
    return withings.status()


@app.post("/api/withings/sync")
def withings_sync():
    try:
        return withings.sync()
    except withings.WithingsError as exc:
        raise HTTPException(400, str(exc)) from exc


# ───────────────────────────── chat (SSE) ─────────────────────────────

class ChatRequest(BaseModel):
    message: str
    persona: str = "coach"
    thread_id: str | None = None


class ResumeRequest(BaseModel):
    thread_id: str
    decision: str  # approve | edit | reject
    goal: dict | None = None


def _config(thread_id: str, persona: str) -> dict:
    return {"configurable": {"thread_id": thread_id}, "run_name": "coach_chat",
            "tags": ["chat", persona], "metadata": {"persona": persona, "thread_id": thread_id}}


async def _stream(graph, payload, config):
    """Translate LangGraph stream events into SSE events the UI understands."""
    try:
        async for mode, chunk in graph.astream(payload, config, stream_mode=["updates", "messages"]):
            if mode == "messages":
                msg, meta = chunk
                if meta.get("langgraph_node") == "generate" and getattr(msg, "content", ""):
                    yield {"event": "token", "data": json.dumps({"t": msg.content})}
                continue
            for node, upd in chunk.items():
                if node == "__interrupt__":
                    yield {"event": "interrupt", "data": json.dumps(upd[0].value, default=str)}
                    continue
                for line in (upd or {}).get("trace", []) if isinstance(upd, dict) else []:
                    if line != "__reset__":
                        yield {"event": "step", "data": json.dumps({"node": node, "text": line})}
                if node == "citation_check" and isinstance(upd, dict) and upd.get("citation_feedback"):
                    yield {"event": "rewrite", "data": "{}"}
        state = (await graph.aget_state(config)).values
        yield {"event": "final", "data": json.dumps({
            "answer": state.get("answer", ""), "citations": state.get("citations", []),
            "route": state.get("route"), "skills": state.get("skills", []), "guard_flags": state.get("guard_flags", []),
            "tool_source": state.get("tool_source"), "cache": state.get("cache_info"),
            "goal_proposal": state.get("goal_proposal"), "goal_result": state.get("goal_result"),
            "attempts": state.get("attempts", 0), "trace": state.get("trace", []),
        }, default=str)}
    except Exception as exc:  # noqa: BLE001
        log.exception("chat failed")
        yield {"event": "error", "data": json.dumps({"message": str(exc)})}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not get_settings().has_openai:
        raise HTTPException(400, "OPENAI_API_KEY is not configured — add it to .env")
    if req.persona not in PERSONAS:
        raise HTTPException(400, f"unknown persona {req.persona}")
    tid = req.thread_id or uuid.uuid4().hex
    return EventSourceResponse(_stream(app.state.graph, initial_input(req.message, req.persona), _config(tid, req.persona)))


@app.post("/api/chat/resume")
async def chat_resume(req: ResumeRequest):
    cfg = _config(req.thread_id, "resume")
    return EventSourceResponse(_stream(app.state.graph, Command(resume={"decision": req.decision, "goal": req.goal}), cfg))
