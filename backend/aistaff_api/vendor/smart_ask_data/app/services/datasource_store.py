from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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


def _default_store_path() -> Path:
    env = os.getenv("SMARTASK_DATASOURCE_STORE_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "storage" / "datasources.json"


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


class DatasourceStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_store_path()
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {"sources": []}
        self._load()

    def _load(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._save()
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw or "{}")
            if isinstance(data, dict) and isinstance(data.get("sources"), list):
                self._data = data
        except Exception:
            self._data = {"sources": []}
            self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def list_sources(self, demo_db_path: str) -> list[DatasourceRecord]:
        with self._lock:
            custom = list(self._data.get("sources") or [])

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
            db_url = (src.get("db_url") or base.get("db_url") or "").strip()
            db_path = ""
            if db_type == "sqlite":
                db_path = os.path.expanduser(
                    str(src.get("db_path") or base.get("db_path") or demo_db_path)
                )
            merged[sid] = {
                "id": sid,
                "name": src.get("name") or base.get("name") or sid,
                "description": src.get("description") or base.get("description") or "",
                "db_type": db_type,
                "tables": tables,
                "db_path": db_path,
                "db_url": db_url if db_type != "sqlite" else "",
            }

        return [DatasourceRecord(**merged[sid]) for sid in order if sid in merged]

    def upsert_source(self, source: dict[str, Any], demo_db_path: str) -> DatasourceRecord:
        sid = validate_identifier(str(source.get("id") or ""), "数据源ID")
        name = (source.get("name") or "").strip()
        desc = (source.get("description") or "").strip()
        raw_tables = source.get("tables") or []
        tables = _unique([validate_identifier(str(t), "表名") for t in raw_tables if str(t).strip()])
        db_type = normalize_db_type(str(source.get("db_type") or "sqlite"))
        db_path = os.path.expanduser(str(source.get("db_path") or "")) or ""
        db_url = (source.get("db_url") or "").strip()

        payload: dict[str, Any] = {"id": sid}
        if name:
            payload["name"] = name
        if desc:
            payload["description"] = desc
        if tables:
            payload["tables"] = tables
        if db_type:
            payload["db_type"] = db_type
        if db_type == "sqlite" and db_path:
            payload["db_path"] = db_path
        if db_type != "sqlite" and db_url:
            payload["db_url"] = db_url

        with self._lock:
            sources = self._data.setdefault("sources", [])
            for item in sources:
                if item.get("id") == sid:
                    if name:
                        item["name"] = name
                    if desc:
                        item["description"] = desc
                    if tables:
                        item["tables"] = _unique(list(item.get("tables") or []) + tables)
                    if db_type:
                        item["db_type"] = db_type
                    if db_type == "sqlite" and db_path:
                        item["db_path"] = db_path
                    if db_type != "sqlite" and db_url:
                        item["db_url"] = db_url
                    self._save()
                    break
            else:
                sources.append(payload)
                self._save()

        # Return merged view (defaults + custom).
        for record in self.list_sources(demo_db_path):
            if record.id == sid:
                return record
        return DatasourceRecord(
            id=sid,
            name=name or sid,
            description=desc,
            tables=tables,
            db_path=db_path or demo_db_path,
            db_type=db_type,
            db_url=db_url,
        )

    def delete_source(self, source_id: str) -> bool:
        sid = (source_id or "").strip()
        if not sid:
            return False
        with self._lock:
            sources = self._data.setdefault("sources", [])
            before = len(sources)
            sources[:] = [s for s in sources if s.get("id") != sid]
            changed = len(sources) != before
            if changed:
                self._save()
            return changed


datasource_store = DatasourceStore()
