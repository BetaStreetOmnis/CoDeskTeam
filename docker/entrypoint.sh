#!/usr/bin/env sh
set -eu

echo "[entrypoint] Running alembic migrations (best-effort)..."
(cd /app/backend && alembic -c alembic.ini upgrade head) || true

cd /app/backend
exec uvicorn jetlinks_ai_api.main:app --host 0.0.0.0 --port 8001
