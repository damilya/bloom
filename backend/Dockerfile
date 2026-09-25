# Shared image for the API and the MCP server (same domain code, different entrypoints).
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend backend
COPY mcp_server mcp_server
COPY skills skills
COPY evals evals
# pre-download the FlashRank reranker (~34 MB) so the first query isn't slow
RUN cd backend && python -c "from flashrank import Ranker; Ranker(model_name='ms-marco-MiniLM-L-12-v2', cache_dir='/app/models')"
ENV PYTHONPATH=/app/backend FLASHRANK_CACHE=/app/models
WORKDIR /app/backend
EXPOSE 8000 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
