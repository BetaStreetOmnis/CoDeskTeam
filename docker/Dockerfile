FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package.json frontend/pnpm-lock.yaml* frontend/
RUN corepack enable && corepack prepare pnpm@latest --activate && cd frontend && pnpm install --frozen-lockfile=false
COPY frontend/ frontend/
RUN cd frontend && pnpm build

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/ /app/backend/
RUN pip install --no-cache-dir --default-timeout=300 --retries 10 uv \
    && cd /app/backend \
    && uv sync --frozen --no-dev

RUN printf '%s\n' '#!/usr/bin/env sh' \
    'exec /opt/host-node20/bin/node /opt/host-node20/bin/codex "$@"' > /usr/local/bin/codex-host \
    && chmod +x /usr/local/bin/codex-host

COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV JETLINKS_AI_UI_DIST_DIR=/app/frontend/dist
ENV PATH=/app/backend/.venv/bin:$PATH
EXPOSE 8001

ENTRYPOINT ["/entrypoint.sh"]
