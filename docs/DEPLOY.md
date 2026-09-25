# Deploying Bloom to Railway (demo data, password-protected)

What you get: one public URL, protected by a shared password (the browser's login prompt), running on the
**demo dataset**. Your real health data never leaves your laptop.

```
browser ──HTTPS + password──► frontend (Next.js, public)  ──private network──► backend (FastAPI + MCP, private)
                                   /api/* is forwarded ─────────────────────────┘      └─ volume /app/data (demo DB, index)
```

The backend has **no public URL**, so nobody can reach the API (or your OpenAI credits) without the password.

Cost: Railway Hobby plan (~$5/month; new accounts get trial credit) + OpenAI usage (≈ $0.01 per research answer).

---

## 1. Create the project (≈ 2 min)

1. Sign in at **https://railway.com** with your GitHub account.
2. **New Project → Deploy from GitHub repo** → pick **`damilya/bloom`** (click *Configure GitHub App* and grant
   access to the repo if it isn't listed).
3. Railway creates one service from the repo. That one becomes the **backend**. Don't worry if its first build
   fails; it needs the settings below.

## 2. Backend service (≈ 5 min)

Click the service → **Settings**:

| Setting | Value |
|---|---|
| Service name (top of Settings) | e.g. `bloom-backend`. Its **private domain** (Settings → Networking, e.g. `illustrious-luck.railway.internal`) is fixed when the service is created and does **not** follow renames |
| Source → Root Directory | leave empty (repo root) |
| Networking → Public Networking | **don't** generate a domain (it stays private) |

**Variables** tab → *Raw Editor* → paste (with your real keys):

```dotenv
PORT=8000
DEMO_MODE=true
OPENAI_API_KEY=sk-...your key...
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2-...your key...
LANGSMITH_PROJECT=bloom-production
DAILY_BUDGET_USD=2
```

`PORT=8000` is required: without it Railway assigns 8080 and the frontend (which calls port 8000) can't connect.

**Volume**: right-click the service (or ⌘K → *Add Volume*) → attach to `backend` → mount path **`/app/data`**.
It keeps the demo database, chat history and research index across redeploys.

Click **Deploy**. In **Deploy Logs** you should see:

```
DEMO_MODE: seeding demo dataset {'measurements': …}
agent tools loaded via mcp
Uvicorn running on http://[::]:8000
```

## 3. Frontend service (≈ 5 min)

1. In the project canvas: **+ Create → GitHub Repo → `damilya/bloom`** again (a second service from the same repo).
2. **Settings**:

| Setting | Value |
|---|---|
| Service name | `frontend` |
| Source → Root Directory | **`frontend`** |
| Networking → Public Networking | **Generate Domain** (target port **3000** if asked) → e.g. `bloom-production.up.railway.app` |

3. **Variables** → Raw Editor:

```dotenv
APP_PASSWORD=choose-a-strong-shared-password
BACKEND_INTERNAL_URL=http://${{bloom-backend.RAILWAY_PRIVATE_DOMAIN}}:8000
```

Replace `bloom-backend` with the backend's service name (Railway autocompletes it after `${{`), or paste the private
domain directly: `http://<name>.railway.internal:8000`. In the single-variable form, the value field takes **only**
the part after `=`, without quotes.

`BACKEND_INTERNAL_URL` is read at runtime by the frontend's proxy (`frontend/src/lib/proxy.ts`), so changing it only
needs a restart. After editing variables, click **Deploy** on the banner: Railway stages variable changes until then.

4. Deploy. When it's green, open the domain. The browser asks for a username (anything) and the password.

## 4. Check it works (2 min)

- **Today** shows the demo dashboard (weight trend with cycle shading).
- **Coach → Integrative Medicine** → "Is fasted morning cardio a bad idea for women with PCOS?" → the answer streams,
  with citation chips.
- **LangSmith** → project `bloom-production` shows the trace.
- Share the URL and password with the mentors (not in the repo!).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/api/status` shows 502 `backend unreachable at http://….railway.internal:` with no port, or a stray `"`/`=` | The value is malformed: a reference like `${{….PORT}}` that resolved to nothing, or pasted quotes. Use a literal `:8000` |
| Pages load but data never appears; `/api/status` shows 503 | `BACKEND_INTERNAL_URL` isn't set on the **frontend** service (or the change wasn't deployed) |
| `/api/status` shows 502 `backend unreachable at http://….railway.internal:8000` | Backend isn't running, or listens on another port: its Deploy Logs must say `Uvicorn running on http://[::]:8000` (the `127.0.0.1:8001` line is the MCP sidecar). Add `PORT=8000` |
| Railway answers `Application not found` | The public domain isn't attached to a running service: check frontend → Settings → Networking (target port 3000) and that its latest deployment is Active |
| Backend build uses "Railpack"/"Nixpacks" instead of the Dockerfile | Settings → Build → Builder: **Dockerfile** (the file is `Dockerfile` at the repo root); Root Directory must be empty |
| Chat says "OPENAI_API_KEY is not configured" | Variable missing/typo on the **backend** service, then redeploy |
| Demo dates look old after weeks | Demo data is seeded once, relative to that day. Delete the volume's `health.db` (or detach and re-attach a fresh volume) and redeploy to reseed |
| No password prompt | `APP_PASSWORD` not set on the **frontend** service |

## Notes

- Withings OAuth isn't configured in the deployment on purpose (demo data only). The Withings connect button
  stays disabled because no Withings keys are set.
- Local development is unchanged: `make dev` (the frontend calls `http://localhost:8000` directly, with no password).
- `docker compose up --build` runs the same images locally (set `DEMO_MODE=true` in `.env` for demo data).
