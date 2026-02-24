#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Pick a free TCP port (best-effort) to avoid "Address already in use".
is_port_free() {
  local port="$1"
  ! lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
}

pick_free_port() {
  local desired="$1"
  local p="${desired}"
  local i
  for i in {0..20}; do
    if is_port_free "${p}"; then
      echo "${p}"
      return 0
    fi
    p="$((p + 1))"
  done
  echo "${desired}"
  return 1
}

# Load repo .env (so JETLINKS_AI_PROVIDER 等能生效；legacy AISTAFF_* 也兼容)
if [ -f "${ROOT_DIR}/.env" ]; then
  PREV_OPENAI_API_KEY="${OPENAI_API_KEY:-}"
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
  # Avoid wiping an already-exported API key when .env leaves it blank.
  if [ -n "${PREV_OPENAI_API_KEY}" ] && [ -z "${OPENAI_API_KEY:-}" ]; then
    export OPENAI_API_KEY="${PREV_OPENAI_API_KEY}"
  fi
fi

PROVIDER="${JETLINKS_AI_PROVIDER:-${AISTAFF_PROVIDER:-}}"
API_PORT="${JETLINKS_AI_API_PORT:-${AISTAFF_API_PORT:-8000}}"
WEB_PORT="${JETLINKS_AI_WEB_PORT:-${AISTAFF_WEB_PORT:-5173}}"
OPENCODE_PORT="${JETLINKS_AI_OPENCODE_PORT:-${AISTAFF_OPENCODE_PORT:-4096}}"
API_HOST="${JETLINKS_AI_API_HOST:-${AISTAFF_API_HOST:-127.0.0.1}}"
WEB_HOST="${JETLINKS_AI_WEB_HOST:-${AISTAFF_WEB_HOST:-127.0.0.1}}"

picked_api_port="$(pick_free_port "${API_PORT}")" || true
if [ "${picked_api_port}" != "${API_PORT}" ]; then
  echo "[jetlinks-ai] port ${API_PORT} is in use; switching api to ${picked_api_port}"
  API_PORT="${picked_api_port}"
fi

picked_web_port="$(pick_free_port "${WEB_PORT}")" || true
if [ "${picked_web_port}" != "${WEB_PORT}" ]; then
  echo "[jetlinks-ai] port ${WEB_PORT} is in use; switching web to ${picked_web_port}"
  WEB_PORT="${picked_web_port}"
fi

if [ "${PROVIDER}" = "opencode" ]; then
  picked_opencode_port="$(pick_free_port "${OPENCODE_PORT}")" || true
  if [ "${picked_opencode_port}" != "${OPENCODE_PORT}" ]; then
    echo "[jetlinks-ai] port ${OPENCODE_PORT} is in use; switching opencode to ${picked_opencode_port}"
    OPENCODE_PORT="${picked_opencode_port}"
  fi
fi

# Export the effective ports/hosts so both backend and frontend can reference the real values
# (especially when we auto-pick a free port).
export JETLINKS_AI_API_HOST="${API_HOST}"
export JETLINKS_AI_API_PORT="${API_PORT}"
export JETLINKS_AI_WEB_HOST="${WEB_HOST}"
export JETLINKS_AI_WEB_PORT="${WEB_PORT}"
export JETLINKS_AI_OPENCODE_PORT="${OPENCODE_PORT}"
# Legacy envs (still supported)
export AISTAFF_API_HOST="${API_HOST}"
export AISTAFF_API_PORT="${API_PORT}"
export AISTAFF_WEB_HOST="${WEB_HOST}"
export AISTAFF_WEB_PORT="${WEB_PORT}"
export AISTAFF_OPENCODE_PORT="${OPENCODE_PORT}"

if [ -z "${OPENAI_API_KEY:-}" ]; then
  # Only prompt when provider needs an LLM key; keep docs/prototype usable without it.
  if [ "${PROVIDER:-openai}" = "openai" ] || [ "${PROVIDER:-openai}" = "opencode" ]; then
    if [ -t 0 ]; then
      echo "[jetlinks-ai] OPENAI_API_KEY is empty; enter it now (input hidden, not saved):"
      read -r -s OPENAI_API_KEY
      echo
      export OPENAI_API_KEY
    fi
  fi
fi

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "[jetlinks-ai] OPENAI_API_KEY is empty (chat will 401)"
else
  echo "[jetlinks-ai] OPENAI_API_KEY is set"
fi
echo "[jetlinks-ai] OPENAI_BASE_URL=${OPENAI_BASE_URL:-}"

LAN_IP=""
if [ "${WEB_HOST}" = "0.0.0.0" ] || [ "${WEB_HOST}" = "::" ]; then
  LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
  if [ -z "${LAN_IP}" ]; then
    LAN_IP="$(ipconfig getifaddr en1 2>/dev/null || true)"
  fi
fi

OPENCODE_PID=""
if [ "${PROVIDER}" = "opencode" ]; then
  OPENCODE_BIN="${OPENCODE_BIN:-}"
  if [ -z "${OPENCODE_BIN}" ]; then
    OPENCODE_BIN="$(command -v opencode 2>/dev/null || true)"
  fi
  if [ -z "${OPENCODE_BIN}" ] && [ -x "${HOME}/.opencode/bin/opencode" ]; then
    OPENCODE_BIN="${HOME}/.opencode/bin/opencode"
  fi

  if [ -z "${OPENCODE_BIN}" ]; then
    echo "[jetlinks-ai] opencode not found; install: curl -fsSL https://opencode.ai/install | bash -s -- --no-modify-path"
  else
    echo "[jetlinks-ai] starting opencode on :${OPENCODE_PORT}"
    # Best-effort: keep dev web/api running even if opencode fails to start.
    set +e
    "${OPENCODE_BIN}" serve --hostname 127.0.0.1 --port "${OPENCODE_PORT}" &
    OPENCODE_PID=$!
    set -e
  fi
fi

echo "[jetlinks-ai] starting api on ${API_HOST}:${API_PORT}"
(cd "${ROOT_DIR}/backend" && uv sync && uv run uvicorn jetlinks_ai_api.main:app --reload --host "${API_HOST}" --port "${API_PORT}") &
API_PID=$!

echo "[jetlinks-ai] starting web on ${WEB_HOST}:${WEB_PORT}"
echo "[jetlinks-ai] web:     http://127.0.0.1:${WEB_PORT}"
echo "[jetlinks-ai] api:     http://127.0.0.1:${API_PORT}/health"
if [ -n "${LAN_IP}" ]; then
  echo "[jetlinks-ai] lan:     http://${LAN_IP}:${WEB_PORT}"
  if [ "${API_HOST}" = "127.0.0.1" ] || [ "${API_HOST}" = "::1" ] || [ "${API_HOST}" = "localhost" ]; then
    echo "[jetlinks-ai] note:    LAN 访问需要把 JETLINKS_AI_API_HOST 也设为 0.0.0.0"
  else
    echo "[jetlinks-ai] api(lan): http://${LAN_IP}:${API_PORT}/health"
  fi
fi
(cd "${ROOT_DIR}/frontend" && pnpm i && JETLINKS_AI_API_HOST="${API_HOST}" JETLINKS_AI_API_PORT="${API_PORT}" AISTAFF_API_HOST="${API_HOST}" AISTAFF_API_PORT="${API_PORT}" pnpm dev --host "${WEB_HOST}" --port "${WEB_PORT}") &
WEB_PID=$!

cleanup() {
  kill "${API_PID}" "${WEB_PID}" 2>/dev/null || true
  if [ -n "${OPENCODE_PID}" ]; then
    kill "${OPENCODE_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Only block on web + api. OpenCode is optional; if it exits it shouldn't stop dev servers.
wait "${API_PID}" "${WEB_PID}"
