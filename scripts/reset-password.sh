#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Load repo .env (so AISTAFF_DB_PATH can be overridden)
if [ -f "${ROOT_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

DB_PATH="${AISTAFF_DB_PATH:-${ROOT_DIR}/.aistaff/aistaff.db}"

if [ ! -f "${DB_PATH}" ]; then
  echo "[aistaff] db not found: ${DB_PATH}"
  echo "[aistaff] tip: set AISTAFF_DB_PATH in .env or start the api once to initialize db"
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[aistaff] uv not found. Install uv first: https://docs.astral.sh/uv/"
  exit 1
fi

EMAIL="${1:-}"
if [ -z "${EMAIL}" ]; then
  echo "[aistaff] existing users:"
  sqlite3 "${DB_PATH}" "select email from users order by id asc;" 2>/dev/null || true
  echo
  echo -n "[aistaff] enter email to reset: "
  read -r EMAIL
fi

EMAIL="$(echo "${EMAIL}" | tr '[:upper:]' '[:lower:]' | xargs)"
if [ -z "${EMAIL}" ]; then
  echo "[aistaff] empty email"
  exit 1
fi

if [ -t 0 ]; then
  echo "[aistaff] enter new password (input hidden):"
  read -r -s NEW_PASS
  echo
  echo "[aistaff] confirm new password:"
  read -r -s NEW_PASS2
  echo
else
  echo "[aistaff] non-interactive shell; set NEW_PASS env var"
  NEW_PASS="${NEW_PASS:-}"
  NEW_PASS2="${NEW_PASS}"
fi

if [ -z "${NEW_PASS:-}" ]; then
  echo "[aistaff] empty password"
  exit 1
fi
if [ "${NEW_PASS}" != "${NEW_PASS2}" ]; then
  echo "[aistaff] password mismatch"
  exit 1
fi

(
  cd "${ROOT_DIR}/backend"
  uv sync >/dev/null
  EMAIL="${EMAIL}" NEW_PASS="${NEW_PASS}" DB_PATH="${DB_PATH}" uv run python - <<'PY'
import os
import sqlite3
from pathlib import Path

from aistaff_api.services.auth_service import hash_password

db_path = Path(os.environ["DB_PATH"]).expanduser().resolve()
email = (os.environ["EMAIL"] or "").strip().lower()
new_pass = os.environ["NEW_PASS"]

pwd_hash = hash_password(new_pass)

conn = sqlite3.connect(str(db_path))
try:
    cur = conn.cursor()
    cur.execute("UPDATE users SET password_hash = ? WHERE lower(email) = ?", (pwd_hash, email))
    if cur.rowcount != 1:
        raise SystemExit(f"no user updated for email={email!r} (rowcount={cur.rowcount})")
    conn.commit()
finally:
    conn.close()

print("ok")
PY
)

echo "[aistaff] password reset ok for: ${EMAIL}"
