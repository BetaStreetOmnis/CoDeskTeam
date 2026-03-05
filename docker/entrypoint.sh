#!/usr/bin/env sh
set -eu

DB_URL="${JETLINKS_AI_DB_URL:-}"

if [ -n "$DB_URL" ]; then
  echo "[entrypoint] Running alembic migrations..."
  (cd /app/backend && alembic -c alembic.ini upgrade head) || true
fi

cd /app/backend
exec uvicorn jetlinks_ai_api.main:app --host 0.0.0.0 --port 8001
