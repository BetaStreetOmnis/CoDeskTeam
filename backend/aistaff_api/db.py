from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Iterable
import re

import aiosqlite

try:
    import asyncpg  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    asyncpg = None

from .config import Settings
from .time_utils import UTC


SCHEMA_VERSION = 10
_ID_RETURNING_TABLES = {
    "users",
    "teams",
    "invites",
    "team_projects",
    "team_requirements",
    "team_skills",
    "team_chatbi_datasources",
    "wecom_apps",
    "feishu_webhooks",
}

_INSERT_RE = re.compile(r"^\s*INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.I)
_INSERT_IGNORE_RE = re.compile(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", re.I)


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


class DbCursor:
    rowcount: int = 0
    lastrowid: int | None = None

    async def fetchone(self) -> Any | None:  # noqa: ANN401
        raise NotImplementedError

    async def fetchall(self) -> list[Any]:  # noqa: ANN401
        raise NotImplementedError

    async def close(self) -> None:
        return None


class SqliteCursor(DbCursor):
    def __init__(self, cursor: aiosqlite.Cursor):
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return int(getattr(self._cursor, "rowcount", 0) or 0)

    @property
    def lastrowid(self) -> int | None:
        value = getattr(self._cursor, "lastrowid", None)
        return int(value) if value is not None else None

    async def fetchone(self) -> aiosqlite.Row | None:
        return await self._cursor.fetchone()

    async def fetchall(self) -> list[aiosqlite.Row]:
        return list(await self._cursor.fetchall())

    async def close(self) -> None:
        await self._cursor.close()


class PgCursor(DbCursor):
    def __init__(self, rows: Iterable[Any] | None, *, rowcount: int = 0, lastrowid: int | None = None) -> None:
        self._rows = list(rows or [])
        self._index = 0
        self._rowcount = int(rowcount)
        self._lastrowid = lastrowid

    @property
    def rowcount(self) -> int:
        return self._rowcount

    @property
    def lastrowid(self) -> int | None:
        return self._lastrowid

    async def fetchone(self) -> Any | None:  # noqa: ANN401
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    async def fetchall(self) -> list[Any]:  # noqa: ANN401
        if self._index == 0:
            self._index = len(self._rows)
            return list(self._rows)
        if self._index >= len(self._rows):
            return []
        out = self._rows[self._index :]
        self._index = len(self._rows)
        return list(out)


class DbConnection:
    kind: str = "sqlite"

    async def execute(self, sql: str, params: tuple | list | None = None) -> DbCursor:
        raise NotImplementedError

    async def commit(self) -> None:
        raise NotImplementedError

    async def rollback(self) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


def _translate_placeholders(sql: str) -> str:
    out: list[str] = []
    idx = 1
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append("''")
                i += 2
                continue
            in_single = not in_single
            out.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            i += 1
            continue
        if ch == "?" and not in_single and not in_double:
            out.append(f"${idx}")
            idx += 1
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _append_on_conflict_do_nothing(sql: str) -> str:
    if "on conflict" in sql.lower():
        return sql
    suffix = ""
    stripped = sql.rstrip()
    if stripped.endswith(";"):
        suffix = ";"
        stripped = stripped[:-1]
    return f"{stripped} ON CONFLICT DO NOTHING{suffix}"


def _rewrite_insert_or_ignore(sql: str) -> str:
    if not _INSERT_IGNORE_RE.match(sql):
        return sql
    rewritten = _INSERT_IGNORE_RE.sub("INSERT INTO ", sql, count=1)
    return _append_on_conflict_do_nothing(rewritten)


def _should_return_id(sql: str) -> bool:
    m = _INSERT_RE.match(sql)
    if not m:
        return False
    table = m.group(1).lower()
    if table not in _ID_RETURNING_TABLES:
        return False
    lowered = sql.lower()
    if "returning" in lowered:
        return False
    if "insert or" in lowered:
        return False
    return True


def _returns_rows(sql: str) -> bool:
    lowered = sql.lstrip().lower()
    return lowered.startswith("select") or lowered.startswith("with") or "returning" in lowered


def _parse_rowcount(status: str) -> int:
    if not status:
        return 0
    parts = status.split()
    for token in reversed(parts):
        if token.isdigit():
            try:
                return int(token)
            except Exception:
                continue
    return 0


class SqliteConnection(DbConnection):
    kind = "sqlite"

    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    async def execute(self, sql: str, params: tuple | list | None = None) -> DbCursor:
        cur = await self._conn.execute(sql, params or ())
        return SqliteCursor(cur)

    async def executescript(self, script: str) -> None:
        await self._conn.executescript(script)

    async def commit(self) -> None:
        await self._conn.commit()

    async def rollback(self) -> None:
        await self._conn.rollback()

    async def close(self) -> None:
        await self._conn.close()


class PostgresConnection(DbConnection):
    kind = "postgres"

    def __init__(self, conn: Any):
        self._conn = conn
        self._in_tx = False

    async def execute(self, sql: str, params: tuple | list | None = None) -> DbCursor:
        raw = (sql or "").strip()
        if not raw:
            return PgCursor([])
        upper = raw.upper()
        if upper == "BEGIN":
            self._in_tx = True
            await self._conn.execute("BEGIN")
            return PgCursor([])
        if upper == "COMMIT":
            self._in_tx = False
            await self._conn.execute("COMMIT")
            return PgCursor([])
        if upper == "ROLLBACK":
            self._in_tx = False
            await self._conn.execute("ROLLBACK")
            return PgCursor([])

        sql = _rewrite_insert_or_ignore(raw)
        if _should_return_id(sql):
            sql = f"{sql} RETURNING id"
        sql = _translate_placeholders(sql)

        params_list = list(params or [])
        if _returns_rows(sql):
            rows = await self._conn.fetch(sql, *params_list)
            lastrowid = None
            if "returning id" in sql.lower() and rows:
                try:
                    lastrowid = int(rows[0].get("id"))  # type: ignore[attr-defined]
                except Exception:
                    lastrowid = None
            return PgCursor(rows, rowcount=len(rows), lastrowid=lastrowid)

        status = await self._conn.execute(sql, *params_list)
        rowcount = _parse_rowcount(str(status))
        return PgCursor([], rowcount=rowcount)

    async def commit(self) -> None:
        if self._in_tx:
            self._in_tx = False
            await self._conn.execute("COMMIT")

    async def rollback(self) -> None:
        if self._in_tx:
            self._in_tx = False
            await self._conn.execute("ROLLBACK")

    async def close(self) -> None:
        await self._conn.close()


async def fetchone(db: DbConnection, sql: str, params: tuple | list | None = None) -> Any | None:  # noqa: ANN401
    cur = await db.execute(sql, params or ())
    try:
        return await cur.fetchone()
    finally:
        await cur.close()


async def fetchall(db: DbConnection, sql: str, params: tuple | list | None = None) -> list[Any]:  # noqa: ANN401
    cur = await db.execute(sql, params or ())
    try:
        return list(await cur.fetchall())
    finally:
        await cur.close()


@asynccontextmanager
async def open_db(settings: Settings) -> AsyncIterator[DbConnection]:
    if settings.db_url and str(settings.db_url).lower().startswith("postgres"):
        if asyncpg is None:
            raise RuntimeError("PostgreSQL 支持未安装，请安装 asyncpg")
        conn = await asyncpg.connect(str(settings.db_url))
        db = PostgresConnection(conn)
        try:
            yield db
        finally:
            await db.close()
        return

    db_path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    raw = await aiosqlite.connect(db_path)
    raw.row_factory = aiosqlite.Row
    await raw.execute("PRAGMA foreign_keys = ON")
    db = SqliteConnection(raw)
    try:
        yield db
    finally:
        await db.close()


async def _sqlite_table_columns(db: DbConnection, table: str) -> set[str]:
    try:
        rows = await fetchall(db, f"PRAGMA table_info({table})")
    except Exception:
        return set()
    cols: set[str] = set()
    for r in rows_to_dicts(list(rows)):
        name = str(r.get("name") or "").strip()
        if name:
            cols.add(name)
    return cols


async def _ensure_team_requirements_delivery_columns(db: DbConnection) -> None:
    if db.kind == "postgres":
        statements = [
            "ALTER TABLE team_requirements ADD COLUMN IF NOT EXISTS delivery_from_team_id BIGINT NULL",
            "ALTER TABLE team_requirements ADD COLUMN IF NOT EXISTS delivery_by_user_id BIGINT NULL",
            "ALTER TABLE team_requirements ADD COLUMN IF NOT EXISTS delivery_state TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE team_requirements ADD COLUMN IF NOT EXISTS delivery_decided_by_user_id BIGINT NULL",
            "ALTER TABLE team_requirements ADD COLUMN IF NOT EXISTS delivery_decided_at TEXT NULL",
        ]
        for stmt in statements:
            await db.execute(stmt)
        return

    cols = await _sqlite_table_columns(db, "team_requirements")
    if not cols:
        return
    if "delivery_from_team_id" not in cols:
        await db.execute("ALTER TABLE team_requirements ADD COLUMN delivery_from_team_id INTEGER NULL")
    if "delivery_by_user_id" not in cols:
        await db.execute("ALTER TABLE team_requirements ADD COLUMN delivery_by_user_id INTEGER NULL")
    if "delivery_state" not in cols:
        await db.execute("ALTER TABLE team_requirements ADD COLUMN delivery_state TEXT NOT NULL DEFAULT ''")
    if "delivery_decided_by_user_id" not in cols:
        await db.execute("ALTER TABLE team_requirements ADD COLUMN delivery_decided_by_user_id INTEGER NULL")
    if "delivery_decided_at" not in cols:
        await db.execute("ALTER TABLE team_requirements ADD COLUMN delivery_decided_at TEXT NULL")


async def init_db(settings: Settings) -> None:
    async with open_db(settings) as db:
        if db.kind == "postgres":
            statements = [
                """
                CREATE TABLE IF NOT EXISTS meta (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS users (
                  id BIGSERIAL PRIMARY KEY,
                  email TEXT NOT NULL UNIQUE,
                  name TEXT NOT NULL,
                  password_hash TEXT NOT NULL,
                  created_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS teams (
                  id BIGSERIAL PRIMARY KEY,
                  name TEXT NOT NULL,
                  created_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS memberships (
                  user_id BIGINT NOT NULL,
                  team_id BIGINT NOT NULL,
                  role TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  PRIMARY KEY (user_id, team_id),
                  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS team_skills (
                  id BIGSERIAL PRIMARY KEY,
                  team_id BIGINT NOT NULL,
                  name TEXT NOT NULL,
                  description TEXT NOT NULL DEFAULT '',
                  content TEXT NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS invites (
                  id BIGSERIAL PRIMARY KEY,
                  team_id BIGINT NOT NULL,
                  email TEXT NULL,
                  role TEXT NOT NULL,
                  token TEXT NOT NULL UNIQUE,
                  created_by BIGINT NULL,
                  created_at TEXT NOT NULL,
                  expires_at TEXT NOT NULL,
                  used_at TEXT NULL,
                  used_by BIGINT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                  FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
                  FOREIGN KEY (used_by) REFERENCES users(id) ON DELETE SET NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS team_projects (
                  id BIGSERIAL PRIMARY KEY,
                  team_id BIGINT NOT NULL,
                  name TEXT NOT NULL,
                  slug TEXT NOT NULL,
                  path TEXT NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(team_id, slug),
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS team_requirements (
                  id BIGSERIAL PRIMARY KEY,
                  team_id BIGINT NOT NULL,
                  project_id BIGINT NULL,
                  source_team TEXT NOT NULL DEFAULT '',
                  title TEXT NOT NULL,
                  description TEXT NOT NULL DEFAULT '',
                  status TEXT NOT NULL DEFAULT 'incoming',
                  priority TEXT NOT NULL DEFAULT 'medium',
                  delivery_from_team_id BIGINT NULL,
                  delivery_by_user_id BIGINT NULL,
                  delivery_state TEXT NOT NULL DEFAULT '',
                  delivery_decided_by_user_id BIGINT NULL,
                  delivery_decided_at TEXT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                  FOREIGN KEY (project_id) REFERENCES team_projects(id) ON DELETE SET NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS team_settings (
                  team_id BIGINT PRIMARY KEY,
                  workspace_path TEXT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS team_chatbi_datasources (
                  id BIGSERIAL PRIMARY KEY,
                  team_id BIGINT NOT NULL,
                  datasource_id TEXT NOT NULL,
                  name TEXT NOT NULL,
                  description TEXT NOT NULL DEFAULT '',
                  db_type TEXT NOT NULL DEFAULT 'sqlite',
                  db_path TEXT NOT NULL DEFAULT '',
                  db_url TEXT NOT NULL DEFAULT '',
                  tables_json TEXT NOT NULL DEFAULT '[]',
                  enabled INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(team_id, datasource_id),
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS wecom_apps (
                  id BIGSERIAL PRIMARY KEY,
                  team_id BIGINT NOT NULL,
                  name TEXT NOT NULL,
                  hook TEXT NOT NULL UNIQUE,
                  corp_id TEXT NOT NULL,
                  agent_id BIGINT NOT NULL,
                  corp_secret TEXT NOT NULL,
                  token TEXT NOT NULL,
                  encoding_aes_key TEXT NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS feishu_webhooks (
                  id BIGSERIAL PRIMARY KEY,
                  team_id BIGINT NOT NULL,
                  name TEXT NOT NULL,
                  hook TEXT NOT NULL UNIQUE,
                  webhook_url TEXT NOT NULL,
                  verification_token TEXT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                  session_id TEXT PRIMARY KEY,
                  team_id BIGINT NOT NULL,
                  user_id BIGINT NOT NULL,
                  role TEXT NOT NULL,
                  provider TEXT NOT NULL,
                  model TEXT NOT NULL,
                  project_id BIGINT NULL,
                  title TEXT NOT NULL DEFAULT '',
                  opencode_session_id TEXT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                  FOREIGN KEY (project_id) REFERENCES team_projects(id) ON DELETE SET NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                  id BIGSERIAL PRIMARY KEY,
                  session_id TEXT NOT NULL,
                  team_id BIGINT NOT NULL,
                  user_id BIGINT NOT NULL,
                  role TEXT NOT NULL,
                  content TEXT NOT NULL,
                  attachments_json TEXT NOT NULL DEFAULT '[]',
                  events_json TEXT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS file_records (
                  file_id TEXT PRIMARY KEY,
                  team_id BIGINT NOT NULL,
                  user_id BIGINT NOT NULL,
                  project_id BIGINT NULL,
                  session_id TEXT NULL,
                  kind TEXT NOT NULL,
                  filename TEXT NOT NULL,
                  content_type TEXT NOT NULL,
                  size_bytes BIGINT NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                  FOREIGN KEY (project_id) REFERENCES team_projects(id) ON DELETE SET NULL,
                  FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE SET NULL
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_team_skills_team_id ON team_skills(team_id)",
                "CREATE INDEX IF NOT EXISTS idx_memberships_team_id ON memberships(team_id)",
                "CREATE INDEX IF NOT EXISTS idx_invites_team_id ON invites(team_id)",
                "CREATE INDEX IF NOT EXISTS idx_invites_token ON invites(token)",
                "CREATE INDEX IF NOT EXISTS idx_team_projects_team_id ON team_projects(team_id)",
                "CREATE INDEX IF NOT EXISTS idx_team_requirements_team_id ON team_requirements(team_id)",
                "CREATE INDEX IF NOT EXISTS idx_team_requirements_project_id ON team_requirements(project_id)",
                "CREATE INDEX IF NOT EXISTS idx_team_chatbi_datasources_team_id ON team_chatbi_datasources(team_id)",
                "CREATE INDEX IF NOT EXISTS idx_wecom_apps_team_id ON wecom_apps(team_id)",
                "CREATE INDEX IF NOT EXISTS idx_wecom_apps_hook ON wecom_apps(hook)",
                "CREATE INDEX IF NOT EXISTS idx_feishu_webhooks_team_id ON feishu_webhooks(team_id)",
                "CREATE INDEX IF NOT EXISTS idx_feishu_webhooks_hook ON feishu_webhooks(hook)",
                "CREATE INDEX IF NOT EXISTS idx_chat_sessions_team_user_updated ON chat_sessions(team_id, user_id, updated_at)",
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id, id)",
                "CREATE INDEX IF NOT EXISTS idx_file_records_team_user_created ON file_records(team_id, user_id, created_at)",
            ]
            for stmt in statements:
                await db.execute(stmt)
        else:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT NOT NULL UNIQUE,
                  name TEXT NOT NULL,
                  password_hash TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS teams (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memberships (
                  user_id INTEGER NOT NULL,
                  team_id INTEGER NOT NULL,
                  role TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  PRIMARY KEY (user_id, team_id),
                  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS team_skills (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  team_id INTEGER NOT NULL,
                  name TEXT NOT NULL,
                  description TEXT NOT NULL DEFAULT '',
                  content TEXT NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS invites (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  team_id INTEGER NOT NULL,
                  email TEXT NULL,
                  role TEXT NOT NULL,
                  token TEXT NOT NULL UNIQUE,
                  created_by INTEGER NULL,
                  created_at TEXT NOT NULL,
                  expires_at TEXT NOT NULL,
                  used_at TEXT NULL,
                  used_by INTEGER NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                  FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
                  FOREIGN KEY (used_by) REFERENCES users(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS team_projects (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  team_id INTEGER NOT NULL,
                  name TEXT NOT NULL,
                  slug TEXT NOT NULL,
                  path TEXT NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(team_id, slug),
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS team_requirements (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  team_id INTEGER NOT NULL,
                  project_id INTEGER NULL,
                  source_team TEXT NOT NULL DEFAULT '',
                  title TEXT NOT NULL,
                  description TEXT NOT NULL DEFAULT '',
                  status TEXT NOT NULL DEFAULT 'incoming',
                  priority TEXT NOT NULL DEFAULT 'medium',
                  delivery_from_team_id INTEGER NULL,
                  delivery_by_user_id INTEGER NULL,
                  delivery_state TEXT NOT NULL DEFAULT '',
                  delivery_decided_by_user_id INTEGER NULL,
                  delivery_decided_at TEXT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                  FOREIGN KEY (project_id) REFERENCES team_projects(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS team_settings (
                  team_id INTEGER PRIMARY KEY,
                  workspace_path TEXT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS team_chatbi_datasources (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  team_id INTEGER NOT NULL,
                  datasource_id TEXT NOT NULL,
                  name TEXT NOT NULL,
                  description TEXT NOT NULL DEFAULT '',
                  db_type TEXT NOT NULL DEFAULT 'sqlite',
                  db_path TEXT NOT NULL DEFAULT '',
                  db_url TEXT NOT NULL DEFAULT '',
                  tables_json TEXT NOT NULL DEFAULT '[]',
                  enabled INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(team_id, datasource_id),
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS wecom_apps (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  team_id INTEGER NOT NULL,
                  name TEXT NOT NULL,
                  hook TEXT NOT NULL UNIQUE,
                  corp_id TEXT NOT NULL,
                  agent_id INTEGER NOT NULL,
                  corp_secret TEXT NOT NULL,
                  token TEXT NOT NULL,
                  encoding_aes_key TEXT NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS feishu_webhooks (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  team_id INTEGER NOT NULL,
                  name TEXT NOT NULL,
                  hook TEXT NOT NULL UNIQUE,
                  webhook_url TEXT NOT NULL,
                  verification_token TEXT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS chat_sessions (
                  session_id TEXT PRIMARY KEY,
                  team_id INTEGER NOT NULL,
                  user_id INTEGER NOT NULL,
                  role TEXT NOT NULL,
                  provider TEXT NOT NULL,
                  model TEXT NOT NULL,
                  project_id INTEGER NULL,
                  title TEXT NOT NULL DEFAULT '',
                  opencode_session_id TEXT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                  FOREIGN KEY (project_id) REFERENCES team_projects(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT NOT NULL,
                  team_id INTEGER NOT NULL,
                  user_id INTEGER NOT NULL,
                  role TEXT NOT NULL,
                  content TEXT NOT NULL,
                  attachments_json TEXT NOT NULL DEFAULT '[]',
                  events_json TEXT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS file_records (
                  file_id TEXT PRIMARY KEY,
                  team_id INTEGER NOT NULL,
                  user_id INTEGER NOT NULL,
                  project_id INTEGER NULL,
                  session_id TEXT NULL,
                  kind TEXT NOT NULL,
                  filename TEXT NOT NULL,
                  content_type TEXT NOT NULL,
                  size_bytes INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                  FOREIGN KEY (project_id) REFERENCES team_projects(id) ON DELETE SET NULL,
                  FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_team_skills_team_id ON team_skills(team_id);
                CREATE INDEX IF NOT EXISTS idx_memberships_team_id ON memberships(team_id);
                CREATE INDEX IF NOT EXISTS idx_invites_team_id ON invites(team_id);
                CREATE INDEX IF NOT EXISTS idx_invites_token ON invites(token);
                CREATE INDEX IF NOT EXISTS idx_team_projects_team_id ON team_projects(team_id);
                CREATE INDEX IF NOT EXISTS idx_team_requirements_team_id ON team_requirements(team_id);
                CREATE INDEX IF NOT EXISTS idx_team_requirements_project_id ON team_requirements(project_id);
                CREATE INDEX IF NOT EXISTS idx_team_chatbi_datasources_team_id ON team_chatbi_datasources(team_id);
                CREATE INDEX IF NOT EXISTS idx_wecom_apps_team_id ON wecom_apps(team_id);
                CREATE INDEX IF NOT EXISTS idx_wecom_apps_hook ON wecom_apps(hook);
                CREATE INDEX IF NOT EXISTS idx_feishu_webhooks_team_id ON feishu_webhooks(team_id);
                CREATE INDEX IF NOT EXISTS idx_feishu_webhooks_hook ON feishu_webhooks(hook);

                CREATE INDEX IF NOT EXISTS idx_chat_sessions_team_user_updated ON chat_sessions(team_id, user_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id, id);
                CREATE INDEX IF NOT EXISTS idx_file_records_team_user_created ON file_records(team_id, user_id, created_at);
                """
            )

        await _ensure_team_requirements_delivery_columns(db)

        await db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)", ("schema_version", "0"))
        row = await fetchone(db, "SELECT value FROM meta WHERE key = ?", ("schema_version",))
        current = int((row_to_dict(row) or {}).get("value") or 0)
        if current < SCHEMA_VERSION:
            await db.execute("UPDATE meta SET value = ? WHERE key = ?", (str(SCHEMA_VERSION), "schema_version"))
        await db.commit()


def row_to_dict(row: Any | None) -> dict[str, Any] | None:  # noqa: ANN401
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    keys = getattr(row, "keys", None)
    if callable(keys):
        return {k: row[k] for k in row.keys()}
    try:
        return dict(row)
    except Exception:
        return None


def rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:  # noqa: ANN401
    out: list[dict[str, Any]] = []
    for r in rows:
        item = row_to_dict(r)
        if item is not None:
            out.append(item)
    return out
