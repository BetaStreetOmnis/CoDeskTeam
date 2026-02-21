#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Migrate aistaff SQLite data into PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
from typing import Iterable

from backend.aistaff_api.config import load_settings
from backend.aistaff_api.db import init_db

try:
    import asyncpg  # type: ignore
except Exception as exc:  # pragma: no cover
    raise SystemExit("asyncpg not installed") from exc


TABLES: list[str] = [
    "meta",
    "users",
    "teams",
    "memberships",
    "team_skills",
    "invites",
    "team_projects",
    "team_requirements",
    "team_settings",
    "wecom_apps",
    "feishu_webhooks",
    "chat_sessions",
    "chat_messages",
    "file_records",
]

ID_TABLES = {
    "users",
    "teams",
    "team_skills",
    "invites",
    "team_projects",
    "team_requirements",
    "wecom_apps",
    "feishu_webhooks",
    "chat_messages",
}


def fetch_rows(conn: sqlite3.Connection, table: str) -> tuple[list[str], list[tuple]]:
    cur = conn.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    return cols, rows


async def insert_rows(pg: asyncpg.Connection, table: str, cols: list[str], rows: Iterable[tuple]) -> None:
    rows = list(rows)
    if not rows:
        return
    placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
    collist = ", ".join(cols)
    sql = f"INSERT INTO {table} ({collist}) VALUES ({placeholders})"
    await pg.executemany(sql, rows)


async def reset_sequence(pg: asyncpg.Connection, table: str) -> None:
    if table not in ID_TABLES:
        return
    await pg.execute(
        f"""
        SELECT setval(
          pg_get_serial_sequence('{table}', 'id'),
          GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 0), 1),
          COALESCE((SELECT MAX(id) FROM {table}), 0) > 0
        )
        """
    )


async def run(sqlite_path: str, pg_url: str) -> None:
    os.environ["AISTAFF_DB_URL"] = pg_url
    settings = load_settings()
    await init_db(settings)

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    pg = await asyncpg.connect(pg_url)
    try:
        await pg.execute("BEGIN")
        for table in TABLES:
            cols, rows = fetch_rows(sqlite_conn, table)
            if not cols:
                continue
            await pg.execute(f"TRUNCATE {table} CASCADE")
            await insert_rows(pg, table, cols, rows)
            await reset_sequence(pg, table)
        await pg.execute("COMMIT")
    except Exception:
        await pg.execute("ROLLBACK")
        raise
    finally:
        await pg.close()
        sqlite_conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate aistaff SQLite data to PostgreSQL")
    parser.add_argument("--sqlite", required=True, help="Path to sqlite db")
    parser.add_argument("--pg", required=True, help="PostgreSQL URL")
    args = parser.parse_args()
    asyncio.run(run(args.sqlite, args.pg))


if __name__ == "__main__":
    main()
