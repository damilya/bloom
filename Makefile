PY := .venv/bin/python
export PYTHONPATH := backend

.PHONY: setup env seed papers index mcp api web dev test lint evals evals-smoke ab sweep report docker

setup:            ## create venv + install backend and frontend deps
	python3.11 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
	cd frontend && npm install

env:              ## create .env from the template (then fill in the TODO keys)
	@test -f .env || cp .env.example .env && echo ".env ready — fill in the TODO values"

seed:             ## load the deterministic demo dataset
	cd backend && ../$(PY) -m app.ingest.seed_demo

papers:           ## download the open-access research corpus
	cd backend && ../$(PY) -m app.rag.fetch

index:            ## parse → chunk → embed → Qdrant (needs OPENAI_API_KEY)
	cd backend && ../$(PY) -m app.rag.index

mcp:              ## MCP server on :8001/mcp
	$(PY) mcp_server/server.py

api:              ## FastAPI on :8000
	cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000

web:              ## Next.js on :3000
	cd frontend && npm run dev

dev:              ## run MCP + API + web together (Ctrl-C stops all)
	@trap 'kill 0' INT; $(MAKE) mcp & $(MAKE) api & $(MAKE) web & wait

test:             ## unit tests (no API key needed)
	cd backend && ../$(PY) -m pytest -q tests

lint:
	.venv/bin/ruff check backend mcp_server evals
	cd frontend && npm run lint && npx tsc --noEmit

evals:            ## full golden set, baseline config
	$(PY) evals/run.py --config baseline

evals-smoke:      ## 10-example smoke eval (what CI runs)
	$(PY) evals/run.py --smoke --min-route-acc 0.9

ab:               ## A/B experiments + prompt evolution
	$(PY) evals/run.py --config baseline ab_mini ab_no_rerank ab_single_query claim_check prompt_v1 no_citation_loop

sweep:            ## temperature / top_p sweep on the evidence subset
	$(PY) evals/run.py --config temp_0 baseline temp_07 top_p_05 --category evidence

report:           ## write results tables into EVALS.md
	$(PY) evals/report.py

docker:           ## everything in containers
	docker compose up --build
