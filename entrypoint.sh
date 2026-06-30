#!/usr/bin/env sh
set -e

echo "[entrypoint] Applying database migrations (alembic upgrade head)..."
alembic upgrade head

echo "[entrypoint] Starting approval-service on :8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
