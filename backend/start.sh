#!/bin/sh
# Container entrypoint: MCP server (sidecar, localhost only) + FastAPI in one service.
set -e
mkdir -p /app/data
# research index ships in the image; copy it onto the persistent volume on first start
if [ ! -f /app/data/index/chunks.jsonl ] && [ -d /app/seed/index ]; then
  mkdir -p /app/data/index && cp /app/seed/index/* /app/data/index/
fi
python /app/mcp_server/server.py &
# "::" listens on IPv6 and IPv4 — Railway's private network is IPv6
exec uvicorn app.main:app --host "${HOST:-::}" --port "${PORT:-8000}"
