# Bloom: notes for Claude Code sessions

Start with README.md (overview + commands), ARCHITECTURE.md (design + trade-offs) and EVALS.md (results + known
failure modes). Below are only the things the code doesn't make obvious.

## Data & privacy (never break these)
- `data/health.db` holds the owner's REAL health data (Withings, Apple Health, Kinetix, Foodvisor). Never commit
  anything under `data/` except `data/index/` (derived from public papers) and the `.gitkeep` files, and never
  seed/clear it: `seed_demo.seed()` WIPES every table. Evals use `data/eval.db`; deployments use `DEMO_MODE=true`.
- Screenshots, slides and the deployed app use demo data only (owner's decision).
- Before any commit, scan the staged files for API keys, Withings credentials and the owner's email.

## Gotchas
- **Timezones:** all sources are normalised to `HOME_TZ` (Europe/Brussels). Apple Health exports stamp records in
  the phone's zone at export time (seen: +05:00), and the laptop clock may also be UTC+5. Never use naive
  local time for imported data.
- **Cross-source duplicates:** Mywellness mirrors Apple Watch workouts and Withings weigh-ins; the Watch re-records
  Kinetix gym visits. `app/ingest/dedupe.py` runs after every import; keep it idempotent.
- **Apple menstrual flow** has two label families (`MenstrualFlow*` old, `VaginalBleeding*` new iOS).
- **Foodvisor summary screens:** the first ring ("Cal over/left") is relative to the goal, not intake. Macro rings
  are "eaten / target". Year-less dates are resolved in code (`resolve_date`), not by the model.
- **Pinned deps:** `mcp<2` (FastMCP API) and `langchain-mcp-adapters<0.2` (needs langchain-core 1.x). Don't bump
  them independently.
- **After a backend change,** restart uvicorn (no `--reload` in the running dev setup); the MCP server
  (`mcp_server/server.py`, :8001) must run for the agent to use MCP (otherwise it falls back to in-process tools).
- **Deployment (Railway):** the frontend proxies `/api/*` and `/withings/*` at runtime (`frontend/src/lib/proxy.ts`);
  don't go back to Next rewrites, which freeze `BACKEND_INTERNAL_URL` at build time. The backend needs `PORT=8000`
  (Railway defaults to 8080). The live URL is in README.md; the password is never in the repo.
- **Eval runs** are slow and cost money (~$1 per full config on the current OpenAI rate tier); run with
  `-u`/`PYTHONUNBUFFERED=1` and in the background. `run.py --config X --langsmith` re-runs X locally first and
  overwrites `evals/results/X.json`.
- **Keynote automation doesn't work on this Mac;** there's no LibreOffice either. The deck is rebuilt with
  `docs/deck/build_deck.js` (needs pptxgenjs on NODE_PATH).
