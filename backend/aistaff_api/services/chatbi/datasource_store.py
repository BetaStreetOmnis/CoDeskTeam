from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...db import fetchall, fetchone, row_to_dict, utc_now_iso
from .remote_db import RemoteDBError, create_engine_from_url, validate_tables


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VALID_DB_TYPES = {"sqlite", "mysql", "postgres"}
_DB_TYPE_ALIASES = {"postgresql": "postgres", "pg": "postgres"}


def validate_identifier(name: str, label: str) -> str:
    name = (name or "").strip()
    if not name or not _IDENT_RE.match(name):
        raise ValueError(f"{label}仅支持字母、数字、下划线，且不能以数字开头")
    return name


def normalize_db_type(raw: str | None) -> str:
    value = (raw or "sqlite").strip().lower()
    value = _DB_TYPE_ALIASES.get(value, value)
    if value not in _VALID_DB_TYPES:
        raise ValueError(f"数据库类型不支持：{raw}")
    return value


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys([i for i in items if i]))


def _loads_json_list(raw: str) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for x in data:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out


_DEFAULT_SOURCES: list[dict[str, Any]] = [
    {
        "id": "alarm",
        "name": "警情/火警库",
        "description": "火警记录、位置、状态、时间等",
        "db_type": "sqlite",
        "tables": ["fire_alarm_record"],
    },
    {
        "id": "personnel",
        "name": "消防人员库",
        "description": "人员、岗位、单位/站点等",
        "db_type": "sqlite",
        "tables": ["fire_personnel"],
    },
    {
        "id": "equipment",
        "name": "装备物资库",
        "description": "装备类型、库存、状态等",
        "db_type": "sqlite",
        "tables": ["fire_equipment"],
    },
    {
        "id": "inspection",
        "name": "监督检查库",
        "description": "单位检查、得分、问题数等",
        "db_type": "sqlite",
        "tables": ["fire_inspection"],
    },
]
DEFAULT_SOURCE_IDS = {str(s.get("id") or "") for s in _DEFAULT_SOURCES if s.get("id")}


@dataclass(frozen=True)
class DatasourceRecord:
    id: str
    name: str
    description: str
    tables: list[str]
    db_path: str
    db_type: str
    db_url: str
    enabled: bool
    is_default: bool


def _ensure_sqlite_tables_exist(db_path: str, tables: list[str]) -> None:
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        exists = {r[0].lower() for r in cur.fetchall()}
    except Exception as e:
        raise ValueError(f"无法读取 SQLite 数据库：{e}") from e
    finally:
        try:
            conn.close()  # type: ignore[maybe-undefined]
        except Exception:
            pass

    missing = [t for t in tables if t.lower() not in exists]
    if missing:
        raise ValueError(f"SQLite 数据库不存在表：{', '.join(missing)}")


async def list_team_sources(db, *, team_id: int, demo_db_path: str) -> list[DatasourceRecord]:  # noqa: ANN001
    rows = await fetchall(
        db,
        """
        SELECT datasource_id, name, description, db_type, db_path, db_url, tables_json, enabled
        FROM team_chatbi_datasources
        WHERE team_id = ?
        ORDER BY datasource_id ASC
        """,
        (int(team_id),),
    )
    custom: list[dict[str, Any]] = []
    for r in rows:
        item = row_to_dict(r) or {}
        custom.append(
            {
                "id": str(item.get("datasource_id") or "").strip(),
                "name": str(item.get("name") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "db_type": str(item.get("db_type") or "").strip(),
                "db_path": str(item.get("db_path") or "").strip(),
                "db_url": str(item.get("db_url") or "").strip(),
                "tables": _loads_json_list(str(item.get("tables_json") or "[]")),
                "enabled": bool(int(item.get("enabled") or 0)),
            }
        )

    order: list[str] = []
    merged: dict[str, dict[str, Any]] = {}

    for src in _DEFAULT_SOURCES:
        sid = str(src.get("id") or "").strip()
        if not sid:
            continue
        order.append(sid)
        merged[sid] = {
            "id": sid,
            "name": src.get("name") or sid,
            "description": src.get("description") or "",
            "db_type": normalize_db_type(str(src.get("db_type") or "sqlite")),
            "tables": _unique(list(src.get("tables") or [])),
            "db_path": demo_db_path,
            "db_url": "",
            "enabled": True,
            "is_default": True,
        }

    for src in custom:
        sid = str(src.get("id") or "").strip()
        if not sid:
            continue
        if sid not in order:
            order.append(sid)
        base = merged.get(sid, {"id": sid, "name": sid, "description": "", "tables": []})
        tables = _unique(list(base.get("tables") or []) + list(src.get("tables") or []))
        try:
            db_type = normalize_db_type(str(src.get("db_type") or base.get("db_type") or "sqlite"))
        except ValueError:
            db_type = "sqlite"
        db_url = str(src.get("db_url") or base.get("db_url") or "").strip()
        db_path = ""
        if db_type == "sqlite":
            db_path = os.path.expanduser(str(src.get("db_path") or base.get("db_path") or demo_db_path))
        merged[sid] = {
            "id": sid,
            "name": src.get("name") or base.get("name") or sid,
            "description": src.get("description") or base.get("description") or "",
            "db_type": db_type,
            "tables": tables,
            "db_path": db_path,
            "db_url": db_url if db_type != "sqlite" else "",
            "enabled": bool(src.get("enabled")) if src.get("enabled") is not None else bool(base.get("enabled", True)),
            "is_default": bool(base.get("is_default")) or (sid in DEFAULT_SOURCE_IDS),
        }

    return [
        DatasourceRecord(
            id=str(merged[sid]["id"]),
            name=str(merged[sid].get("name") or sid),
            description=str(merged[sid].get("description") or ""),
            tables=list(merged[sid].get("tables") or []),
            db_path=str(merged[sid].get("db_path") or demo_db_path),
            db_type=str(merged[sid].get("db_type") or "sqlite"),
            db_url=str(merged[sid].get("db_url") or ""),
            enabled=bool(merged[sid].get("enabled", True)),
            is_default=bool(merged[sid].get("is_default", False)),
        )
        for sid in order
        if sid in merged
    ]


async def upsert_team_source(db, *, team_id: int, demo_db_path: str, source: dict[str, Any]) -> DatasourceRecord:  # noqa: ANN001
    sid = validate_identifier(str(source.get("id") or ""), "数据源ID")
    name = (source.get("name") or "").strip()
    description = (source.get("description") or "").strip()
    raw_tables = source.get("tables") or []
    tables = _unique([validate_identifier(str(t), "表名") for t in raw_tables if str(t).strip()])
    db_type = normalize_db_type(str(source.get("db_type") or "sqlite"))
    db_path = os.path.expanduser(str(source.get("db_path") or "")) or ""
    db_url = (source.get("db_url") or "").strip()
    enabled = bool(source.get("enabled", True))

    # Require name only for brand new custom sources (defaults already have a display name).
    existing_row = await fetchone(
        db,
        "SELECT datasource_id FROM team_chatbi_datasources WHERE team_id = ? AND datasource_id = ?",
        (int(team_id), sid),
    )
    exists = bool(row_to_dict(existing_row))
    if not exists and sid not in DEFAULT_SOURCE_IDS and not name:
        raise ValueError("数据源名称不能为空")

    if db_type != "sqlite":
        if not db_url:
            raise ValueError("请填写数据库连接地址")
        if not tables:
            raise ValueError("请至少指定一张表")
        engine = None
        try:
            engine = create_engine_from_url(db_url)
            missing = validate_tables(engine, tables)
        except RemoteDBError as e:
            raise ValueError(str(e)) from e
        except Exception as e:
            raise ValueError(f"数据库连接失败：{e}") from e
        finally:
            if engine is not None:
                engine.dispose()
        if missing:
            raise ValueError(f"数据库不存在表：{', '.join(missing)}")
    else:
        # Default to demo DB if not provided.
        if not db_path:
            db_path = demo_db_path
        db_path = str(Path(db_path).expanduser())
        if not Path(db_path).exists():
            raise ValueError("SQLite 数据库文件不存在")
        if not tables:
            raise ValueError("请至少指定一张表")
        _ensure_sqlite_tables_exist(db_path, tables)
        db_url = ""

    now = utc_now_iso()

    if exists:
        await db.execute(
            """
            UPDATE team_chatbi_datasources
            SET name = COALESCE(NULLIF(?, ''), name),
                description = ?,
                db_type = ?,
                db_path = ?,
                db_url = ?,
                tables_json = ?,
                enabled = ?,
                updated_at = ?
            WHERE team_id = ? AND datasource_id = ?
            """,
            (
                name,
                description,
                db_type,
                db_path if db_type == "sqlite" else "",
                db_url if db_type != "sqlite" else "",
                json.dumps(tables, ensure_ascii=False),
                1 if enabled else 0,
                now,
                int(team_id),
                sid,
            ),
        )
    else:
        await db.execute(
            """
            INSERT INTO team_chatbi_datasources(
              team_id, datasource_id, name, description, db_type, db_path, db_url, tables_json, enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(team_id),
                sid,
                name or sid,
                description,
                db_type,
                db_path if db_type == "sqlite" else "",
                db_url if db_type != "sqlite" else "",
                json.dumps(tables, ensure_ascii=False),
                1 if enabled else 0,
                now,
                now,
            ),
        )
    await db.commit()

    # Return merged view
    sources = await list_team_sources(db, team_id=int(team_id), demo_db_path=demo_db_path)
    for rec in sources:
        if rec.id == sid:
            return rec
    # Shouldn't happen, but keep API predictable.
    return DatasourceRecord(
        id=sid,
        name=name or sid,
        description=description,
        tables=tables,
        db_path=db_path,
        db_type=db_type,
        db_url=db_url,
        enabled=enabled,
        is_default=(sid in DEFAULT_SOURCE_IDS),
    )


async def delete_team_source(db, *, team_id: int, source_id: str) -> bool:  # noqa: ANN001
    sid = validate_identifier(str(source_id or ""), "数据源ID")
    if sid in DEFAULT_SOURCE_IDS:
        raise ValueError("系统内置数据源不允许删除")
    cur = await db.execute(
        "DELETE FROM team_chatbi_datasources WHERE team_id = ? AND datasource_id = ?",
        (int(team_id), sid),
    )
    await db.commit()
    return bool(cur.rowcount)

