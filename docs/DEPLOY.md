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
| Service name (top of Settings) | `backend` ← the frontend reaches it at `backend.railway.internal`, so keep this exact name |
| Source → Root Directory | leave empty (repo root) |
| Networking → Public Networking | **don't** generate a domain (it stays private) |

**Variables** tab → *Raw Editor* → paste (with your real keys):

```dotenv
RAILWAY_DOCKERFILE_PATH=backend/Dockerfile
PORT=8000
DEMO_MODE=true
OPENAI_API_KEY=sk-...your key...
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2-...your key...
LANGSMITH_PROJECT=bloom-production
DAILY_BUDGET_USD=2
```

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
BACKEND_INTERNAL_URL=http://backend.railway.internal:8000
```

`BACKEND_INTERNAL_URL` is used **at build time**, so if you change it later, redeploy the frontend.

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
| Frontend pages load, but every API call is 502/500 | Backend isn't named exactly `backend`, isn't running, or `PORT=8000` is missing. Check `BACKEND_INTERNAL_URL`, then redeploy the **frontend** (rewrites are baked at build) |
| Backend build: "Dockerfile not found" | `RAILWAY_DOCKERFILE_PATH=backend/Dockerfile` missing on the backend service |
| Chat says "OPENAI_API_KEY is not configured" | Variable missing/typo on the **backend** service, then redeploy |
| Demo dates look old after weeks | Demo data is seeded once, relative to that day. Delete the volume's `health.db` (or detach and re-attach a fresh volume) and redeploy to reseed |
| No password prompt | `APP_PASSWORD` not set on the **frontend** service |

## Notes

- Withings OAuth isn't configured in the deployment on purpose (demo data only). The Withings connect button
  stays disabled because no Withings keys are set.
- Local development is unchanged: `make dev` (the frontend calls `http://localhost:8000` directly, with no password).
- `docker compose up --build` runs the same images locally (set `DEMO_MODE=true` in `.env` for demo data).
