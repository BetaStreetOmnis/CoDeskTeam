from __future__ import annotations

import json
import re
import sqlite3
from typing import Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.auth import get_session_user
from app.core.settings import get_settings
from app.services.datasource_store import (
    DEFAULT_SOURCE_IDS,
    datasource_store,
    normalize_db_type,
    validate_identifier,
)
from app.services.demo_db import ensure_demo_db
from app.services.query_engine import QueryEngine
from app.services.remote_db import RemoteDBError, create_engine_from_url, validate_tables
from app.services.store import store
from app.services.user_store import user_store


router = APIRouter(tags=["smart_ask"])


class LoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    question: str | None = None
    query: str | None = None
    datasource_ids: list[str] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)


class SQLRunRequest(BaseModel):
    sql: str
    datasource_ids: list[str] = Field(default_factory=list)
    question: str | None = None


def _current_user(request: Request) -> dict:
    username = get_session_user(request)
    if not username:
        raise HTTPException(status_code=401, detail="未登录")
    user = user_store.get_user(username)
    if not user:
        request.session.clear()
        raise HTTPException(status_code=401, detail="账号不存在")
    return {
        "username": user.username,
        "role": user.role,
        "allowed_datasource_ids": list(user.allowed_datasource_ids or []),
        "is_guest": False,
    }


def _require_admin(request: Request) -> dict:
    user = _current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    return user


def _filter_allowed_ids(user: dict, ids: list[str]) -> list[str]:
    allowed = set(user.get("allowed_datasource_ids") or [])
    if "*" in allowed or "all" in allowed:
        return list(ids)
    return [sid for sid in ids if sid in allowed]


def _normalize_text(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", (text or "").lower())


def _is_smalltalk(question: str) -> bool:
    text = _normalize_text(question)
    if not text:
        return True
    greetings = {
        "你好",
        "您好",
        "嗨",
        "哈喽",
        "hello",
        "hi",
        "hey",
        "早上好",
        "下午好",
        "晚上好",
        "在吗",
        "在么",
        "再见",
        "拜拜",
        "bye",
        "谢谢",
        "多谢",
    }
    if text in greetings:
        return True
    if text.startswith("你好") and len(text) <= 4:
        return True
    return False


def _smalltalk_reply(question: str) -> str:
    text = _normalize_text(question)
    if text in {"谢谢", "多谢"}:
        return "不客气！需要查询数据或生成图表，直接告诉我。"
    if text in {"再见", "拜拜", "bye"}:
        return "好的，再见！需要时随时来。"
    return "你好！我可以帮你查询数据或生成图表，比如：按月统计火警趋势。"


def _sse_pack(event: str, payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


@router.post("/auth/login")
def login(request: Request, payload: LoginRequest):
    user = user_store.verify_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    request.session["user"] = user.username
    request.session["role"] = user.role
    return {"success": True, "user": {"username": user.username, "role": user.role}}


@router.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"success": True}


@router.get("/auth/me")
def me(request: Request):
    user = _current_user(request)
    return {"success": True, "user": {"username": user["username"], "role": user["role"], "is_guest": user["is_guest"]}}


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = Field(default="user")
    allowed_datasource_ids: list[str] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    password: str | None = None
    role: str | None = None
    allowed_datasource_ids: list[str] | None = None


@router.get("/auth/users")
def list_users(request: Request):
    _require_admin(request)
    users = user_store.list_users()
    return {
        "success": True,
        "data": [
            {
                "username": u.username,
                "role": u.role,
                "allowed_datasource_ids": list(u.allowed_datasource_ids or []),
            }
            for u in users
        ],
    }


@router.post("/auth/users")
def create_user(request: Request, payload: UserCreateRequest):
    _require_admin(request)
    try:
        user = user_store.create_user(
            payload.username,
            payload.password,
            role=payload.role,
            allowed_datasource_ids=payload.allowed_datasource_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, "data": {"username": user.username, "role": user.role}}


@router.put("/auth/users/{username}")
def update_user(request: Request, username: str, payload: UserUpdateRequest):
    _require_admin(request)
    target = user_store.get_user(username)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if payload.role is not None and target.role == "admin" and (payload.role or "user") != "admin":
        if user_store.count_admins() <= 1:
            raise HTTPException(status_code=400, detail="至少保留一个管理员")
    user = user_store.update_user(
        username,
        password=payload.password,
        role=payload.role,
        allowed_datasource_ids=payload.allowed_datasource_ids,
    )
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"success": True, "data": {"username": user.username, "role": user.role}}


@router.delete("/auth/users/{username}")
def delete_user(request: Request, username: str):
    me = _require_admin(request)
    if username == me["username"]:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    target = user_store.get_user(username)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.role == "admin" and user_store.count_admins() <= 1:
        raise HTTPException(status_code=400, detail="至少保留一个管理员")
    if not user_store.delete_user(username):
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"success": True}


@router.get("/datasources")
def datasources(request: Request):
    user = _current_user(request)
    settings = get_settings()
    sources = datasource_store.list_sources(settings.demo_db_path)
    all_sources: list[dict[str, Any]] = []
    for src in sources:
        all_sources.append(
            {
                "id": src.id,
                "name": src.name,
                "description": src.description,
                "db_type": src.db_type,
                "tables": list(src.tables),
                "db_path": src.db_path,
                "db_url": src.db_url,
                "is_default": src.id in DEFAULT_SOURCE_IDS,
            }
        )

    for src in all_sources:
        total = 0
        conn = None
        try:
            if src.get("db_type") != "sqlite":
                src["row_count"] = None
                continue
            conn = sqlite3.connect(src["db_path"])
            cur = conn.cursor()
            for t in src.get("tables", []):
                try:
                    cur.execute(f'SELECT COUNT(*) FROM "{t}"')
                    total += int(cur.fetchone()[0])
                except Exception:
                    pass
            src["row_count"] = total
        except Exception:
            src["row_count"] = None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    allowed_ids = _filter_allowed_ids(user, [s["id"] for s in all_sources])
    data = [s for s in all_sources if s["id"] in allowed_ids]
    for src in data:
        src.pop("db_path", None)
        src.pop("db_url", None)
    return {"success": True, "data": data}


class ColumnDef(BaseModel):
    name: str
    type: str = Field(default="TEXT")


class TableCreateRequest(BaseModel):
    name: str
    columns: list[ColumnDef]
    rows: list[dict[str, Any]] = Field(default_factory=list)


class DatasourceCreateRequest(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    db_type: str | None = None
    db_path: str | None = None
    db_url: str | None = None
    tables: list[str] = Field(default_factory=list)
    create_table: TableCreateRequest | None = None


_VALID_COLUMN_TYPES = {"TEXT", "INTEGER", "REAL", "NUMERIC", "BLOB"}


def _require_identifier(name: str, label: str) -> str:
    try:
        return validate_identifier(name, label)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _normalize_column_type(raw: str) -> str:
    t = (raw or "").strip().upper() or "TEXT"
    if t not in _VALID_COLUMN_TYPES:
        raise HTTPException(status_code=400, detail=f"字段类型不支持：{t}")
    return t


def _create_table(db_path: str, table_name: str, columns: list[ColumnDef], rows: list[dict[str, Any]]) -> None:
    if not columns:
        raise HTTPException(status_code=400, detail="字段不能为空")

    col_names: list[str] = []
    col_defs: list[str] = []
    for col in columns:
        name = _require_identifier(col.name, "字段名")
        if name in col_names:
            raise HTTPException(status_code=400, detail=f"字段重复：{name}")
        col_names.append(name)
        col_type = _normalize_column_type(col.type)
        col_defs.append(f'"{name}" {col_type}')

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    try:
        cur = conn.cursor()
        cur.execute(
            f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(col_defs)})'
        )
        if rows:
            cols_sql = ", ".join(f'"{c}"' for c in col_names)
            placeholders = ", ".join("?" for _ in col_names)
            sql = f'INSERT INTO "{table_name}" ({cols_sql}) VALUES ({placeholders})'
            for row in rows:
                cur.execute(sql, [row.get(c) for c in col_names])
        conn.commit()
    except sqlite3.OperationalError as e:
        raise HTTPException(status_code=400, detail=f"建表失败：{e}") from e
    finally:
        conn.close()


def _ensure_tables_exist(db_path: str, tables: list[str]) -> None:
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        exists = {r[0].lower() for r in cur.fetchall()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法读取数据库：{e}") from e
    finally:
        try:
            conn.close()  # type: ignore[maybe-undefined]
        except Exception:
            pass

    missing = [t for t in tables if t.lower() not in exists]
    if missing:
        raise HTTPException(status_code=400, detail=f"数据库不存在表：{', '.join(missing)}")


@router.post("/datasources")
def create_datasource(request: Request, payload: DatasourceCreateRequest):
    _current_user(request)
    settings = get_settings()

    source_id = _require_identifier(payload.id, "数据源ID")
    name = (payload.name or "").strip()
    description = (payload.description or "").strip()
    try:
        db_type = normalize_db_type(payload.db_type or "sqlite")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db_url = (payload.db_url or "").strip()
    db_path = str(Path(payload.db_path or settings.demo_db_path).expanduser())
    tables = [_require_identifier(str(t), "表名") for t in payload.tables if str(t).strip()]

    existing_ids = {s.id for s in datasource_store.list_sources(settings.demo_db_path)}
    if source_id not in existing_ids and not name:
        raise HTTPException(status_code=400, detail="数据源名称不能为空")

    if db_type != "sqlite":
        if payload.create_table:
            raise HTTPException(status_code=400, detail="当前仅支持SQLite建表")
        if not db_url:
            raise HTTPException(status_code=400, detail="请填写数据库连接地址")
        if not tables:
            raise HTTPException(status_code=400, detail="请至少指定一张表")
        engine = None
        try:
            engine = create_engine_from_url(db_url)
            missing = validate_tables(engine, tables)
        except RemoteDBError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"数据库连接失败：{e}") from e
        finally:
            if engine is not None:
                engine.dispose()
        if missing:
            raise HTTPException(status_code=400, detail=f"数据库不存在表：{', '.join(missing)}")

        record = datasource_store.upsert_source(
            {
                "id": source_id,
                "name": name,
                "description": description,
                "db_type": db_type,
                "db_url": db_url,
                "tables": tables,
            },
            settings.demo_db_path,
        )
    else:
        if payload.create_table:
            table_name = _require_identifier(payload.create_table.name, "表名")
            _create_table(db_path, table_name, payload.create_table.columns, payload.create_table.rows)
            if table_name not in tables:
                tables.append(table_name)

        if not tables:
            raise HTTPException(status_code=400, detail="请至少指定一张表")

        if not Path(db_path).exists():
            raise HTTPException(status_code=400, detail="数据库文件不存在")

        _ensure_tables_exist(db_path, tables)

        record = datasource_store.upsert_source(
            {
                "id": source_id,
                "name": name,
                "description": description,
                "db_type": db_type,
                "db_path": db_path if db_path != settings.demo_db_path else "",
                "tables": tables,
            },
            settings.demo_db_path,
        )
    return {
        "success": True,
        "data": {
            "id": record.id,
            "name": record.name,
            "description": record.description,
            "tables": list(record.tables),
        },
    }


@router.delete("/datasources/{source_id}")
def delete_datasource(request: Request, source_id: str):
    _current_user(request)
    sid = _require_identifier(source_id, "数据源ID")
    if sid in DEFAULT_SOURCE_IDS:
        raise HTTPException(status_code=400, detail="系统内置数据源不允许删除")
    if not datasource_store.delete_source(sid):
        raise HTTPException(status_code=404, detail="数据源不存在")
    return {"success": True}


@router.get("/examples")
def examples():
    return {
        "success": True,
        "examples": [
            "查询最近7天的火警记录",
            "查看今天未处理的火警",
            "统计各个单位的火警数量排名前10",
            "按月统计火警趋势",
            "各站点装备库存TOP10",
            "按单位统计监督检查得分",
            "哪个位置的火警最多？",
            "各站点人员数量与装备库存对比（多源联动）",
            "近30天各单位火警数量与监督检查得分对比（多源联动）",
            "先查最近7天火警记录，然后说：再按单位统计一下（上下文）",
            "在上一问基础上再说：只看未处理的（上下文）",
            "先在「数据开发」运行“警情实时接入”，再问：今天未处理的火警（端到端联动）",
        ],
    }


@router.get("/metrics")
def metrics(request: Request):
    _current_user(request)
    settings = get_settings()

    def q1(cur: sqlite3.Cursor, sql: str, params: tuple = ()) -> int:
        cur.execute(sql, params)
        val = cur.fetchone()
        if not val:
            return 0
        v = val[0]
        if v is None:
            return 0
        return int(v)

    def qf(cur: sqlite3.Cursor, sql: str, params: tuple = ()) -> float | None:
        cur.execute(sql, params)
        val = cur.fetchone()
        if not val:
            return None
        v = val[0]
        if v is None:
            return None
        try:
            return float(v)
        except Exception:
            return None

    try:
        conn = sqlite3.connect(settings.demo_db_path)
        cur = conn.cursor()

        alarm_total = q1(cur, "SELECT COUNT(*) FROM fire_alarm_record")
        alarm_7d = q1(cur, "SELECT COUNT(*) FROM fire_alarm_record WHERE create_time >= (strftime('%s','now','-7 day') * 1000)")
        alarm_today = q1(
            cur,
            "SELECT COUNT(*) FROM fire_alarm_record WHERE date(datetime(create_time/1000,'unixepoch','localtime')) = date('now','localtime')",
        )
        alarm_unprocessed = q1(cur, "SELECT COUNT(*) FROM fire_alarm_record WHERE processing_state = '未处理'")
        alarm_unprocessed_today = q1(
            cur,
            "SELECT COUNT(*) FROM fire_alarm_record WHERE processing_state = '未处理' AND date(datetime(create_time/1000,'unixepoch','localtime')) = date('now','localtime')",
        )

        personnel_total = q1(cur, "SELECT COUNT(*) FROM fire_personnel")
        equipment_total_qty = q1(cur, "SELECT COALESCE(SUM(quantity), 0) FROM fire_equipment")
        equipment_in_stock_qty = q1(cur, "SELECT COALESCE(SUM(quantity), 0) FROM fire_equipment WHERE status = '在库'")

        inspection_30d = q1(cur, "SELECT COUNT(*) FROM fire_inspection WHERE inspection_date >= date('now','-30 day')")
        inspection_issues_30d = q1(
            cur,
            "SELECT COALESCE(SUM(issues_count), 0) FROM fire_inspection WHERE inspection_date >= date('now','-30 day')",
        )
        inspection_avg_score_30d = qf(
            cur,
            "SELECT ROUND(AVG(score), 1) FROM fire_inspection WHERE inspection_date >= date('now','-30 day')",
        )

        conn.close()
    except Exception:
        alarm_total = alarm_7d = alarm_today = alarm_unprocessed = alarm_unprocessed_today = 0
        personnel_total = equipment_total_qty = equipment_in_stock_qty = 0
        inspection_30d = inspection_issues_30d = 0
        inspection_avg_score_30d = None

    return {
        "success": True,
        "data": {
            "alarm_total": alarm_total,
            "alarm_7d": alarm_7d,
            "alarm_today": alarm_today,
            "alarm_unprocessed": alarm_unprocessed,
            "alarm_unprocessed_today": alarm_unprocessed_today,
            "personnel_total": personnel_total,
            "equipment_total_qty": equipment_total_qty,
            "equipment_in_stock_qty": equipment_in_stock_qty,
            "inspection_30d": inspection_30d,
            "inspection_issues_30d": inspection_issues_30d,
            "inspection_avg_score_30d": inspection_avg_score_30d,
        },
    }


@router.post("/chat")
async def chat(request: Request, payload: ChatRequest):
    user = _current_user(request)
    question = (payload.question or payload.query or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    settings = get_settings()
    engine = QueryEngine(settings=settings)
    intent = await engine.classify_intent(question, payload.history)
    if intent == "chat" or (intent == "unknown" and _is_smalltalk(question)):
        reply = await engine.chat(question, payload.history)
        if not reply:
            reply = _smalltalk_reply(question)
        return {"success": True, "mode": "chat", "reply": reply, "question": question}

    datasource_ids = payload.datasource_ids
    if not datasource_ids:
        ds = datasources(request)
        datasource_ids = [item["id"] for item in ds["data"]]
    else:
        datasource_ids = _filter_allowed_ids(user, datasource_ids)
        if not datasource_ids:
            raise HTTPException(status_code=403, detail="没有权限访问所选数据源")

    result = await engine.ask(
        question=question,
        datasource_ids=datasource_ids,
        history=payload.history,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "查询失败"))

    result_id = store.save_result(request, result)
    result["result_id"] = result_id
    return result


@router.post("/chat/stream")
async def chat_stream(request: Request, payload: ChatRequest):
    user = _current_user(request)
    question = (payload.question or payload.query or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    settings = get_settings()
    engine = QueryEngine(settings=settings)
    intent = await engine.classify_intent(question, payload.history)

    async def _stream_chat():
        if intent == "chat" or (intent == "unknown" and _is_smalltalk(question)):
            reply = await engine.chat(question, payload.history)
            if not reply:
                reply = _smalltalk_reply(question)
            yield _sse_pack("chat", {"success": True, "mode": "chat", "reply": reply, "question": question})
            yield _sse_pack("done", {"success": True})
            return

        datasource_ids = payload.datasource_ids
        if not datasource_ids:
            ds = datasources(request)
            datasource_ids = [item["id"] for item in ds["data"]]
        else:
            datasource_ids = _filter_allowed_ids(user, datasource_ids)
            if not datasource_ids:
                yield _sse_pack("error", {"error": "没有权限访问所选数据源"})
                yield _sse_pack("done", {"success": False})
                return

        async for item in engine.ask_stream(
            question=question,
            datasource_ids=datasource_ids,
            history=payload.history,
        ):
            kind = item.get("type")
            if kind == "sql_delta":
                yield _sse_pack("sql_delta", {"delta": item.get("delta", "")})
            elif kind == "sql":
                yield _sse_pack("sql", {"sql": item.get("sql", "")})
            elif kind == "sql_explain_delta":
                yield _sse_pack("sql_explain_delta", {"delta": item.get("delta", "")})
            elif kind == "sql_explain":
                yield _sse_pack("sql_explain", {"sql_explain": item.get("sql_explain", "")})
            elif kind == "analysis_delta":
                yield _sse_pack("analysis_delta", {"delta": item.get("delta", "")})
            elif kind == "analysis":
                yield _sse_pack("analysis", {"analysis": item.get("analysis", "")})
            elif kind == "result":
                result = item.get("result") or {}
                result_id = store.save_result(request, result)
                result["result_id"] = result_id
                yield _sse_pack("result", {"result": result})
            elif kind == "error":
                yield _sse_pack("error", {"error": item.get("error", "查询失败")})

        yield _sse_pack("done", {"success": True})

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(_stream_chat(), media_type="text/event-stream", headers=headers)


@router.post("/sql/run")
async def run_sql(request: Request, payload: SQLRunRequest):
    user = _current_user(request)
    settings = get_settings()
    engine = QueryEngine(settings=settings)

    datasource_ids = payload.datasource_ids
    if not datasource_ids:
        ds = datasources(request)
        datasource_ids = [item["id"] for item in ds["data"]]
    else:
        datasource_ids = _filter_allowed_ids(user, datasource_ids)
        if not datasource_ids:
            raise HTTPException(status_code=403, detail="没有权限访问所选数据源")

    result = await engine.run_sql(
        sql=payload.sql,
        datasource_ids=datasource_ids,
        question=(payload.question or "").strip() or None,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "执行失败"))

    result_id = store.save_result(request, result)
    result["result_id"] = result_id
    return result


class PinRequest(BaseModel):
    result_id: str
    chart: dict[str, Any] | None = None


@router.post("/charts/pin")
def pin_chart(request: Request, payload: PinRequest):
    _current_user(request)
    try:
        if payload.chart:
            store.update_chart(request, payload.result_id, payload.chart)
        store.pin(request, payload.result_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"success": True}


@router.get("/charts")
def list_charts(request: Request):
    _current_user(request)
    charts = store.list_pins(request)
    return {"success": True, "data": charts}


@router.delete("/charts/{result_id}")
def unpin_chart(request: Request, result_id: str):
    _current_user(request)
    store.unpin(request, result_id)
    return {"success": True}


@router.post("/demo/seed-dashboard")
async def seed_dashboard(request: Request):
    user = _current_user(request)

    existing = store.list_pins(request)
    if existing:
        return {"success": True, "data": existing}

    settings = get_settings()
    engine = QueryEngine(settings=settings)

    allowed = set(user["allowed_datasource_ids"])
    seeds: list[tuple[str, str, list[str]]] = []

    if "alarm" in allowed:
        seeds.extend(
            [
                (
                    "按月统计火警趋势",
                    "SELECT strftime('%Y-%m', datetime(create_time/1000,'unixepoch','localtime')) AS 月份, "
                    "COUNT(*) AS 火警数量 "
                    "FROM fire_alarm_record "
                    "WHERE create_time >= (strftime('%s','now','-365 day') * 1000) "
                    "GROUP BY 月份 ORDER BY 月份 LIMIT 24",
                    ["alarm"],
                ),
                (
                    "近7天火警处理状态占比",
                    "SELECT processing_state AS 处理状态, COUNT(*) AS 数量 "
                    "FROM fire_alarm_record "
                    "WHERE create_time >= (strftime('%s','now','-7 day') * 1000) "
                    "GROUP BY processing_state ORDER BY 数量 DESC",
                    ["alarm"],
                ),
                (
                    "报警位置TOP10",
                    "SELECT alarm_location AS 报警位置, COUNT(*) AS 报警次数 "
                    "FROM fire_alarm_record "
                    "GROUP BY alarm_location ORDER BY 报警次数 DESC LIMIT 10",
                    ["alarm"],
                ),
                (
                    "火警数量TOP10单位",
                    "SELECT unit_name AS 单位, COUNT(*) AS 火警数量 "
                    "FROM fire_alarm_record "
                    "GROUP BY unit_name ORDER BY 火警数量 DESC LIMIT 10",
                    ["alarm"],
                ),
            ]
        )

    if "equipment" in allowed:
        seeds.append(
            (
                "各站点装备总库存",
                "SELECT station AS 站点, SUM(quantity) AS 库存数量 "
                "FROM fire_equipment "
                "GROUP BY station ORDER BY 库存数量 DESC",
                ["equipment"],
            )
        )

    if "inspection" in allowed:
        seeds.append(
            (
                "按单位统计监督检查平均得分",
                "SELECT unit_name AS 单位, ROUND(AVG(score), 1) AS 平均得分, SUM(issues_count) AS 问题总数 "
                "FROM fire_inspection "
                "GROUP BY unit_name ORDER BY 平均得分 DESC LIMIT 10",
                ["inspection"],
            )
        )

    if "personnel" in allowed:
        seeds.append(
            (
                "各站点人员数量",
                "SELECT station AS 站点, COUNT(*) AS 人员数量 "
                "FROM fire_personnel "
                "GROUP BY station ORDER BY 人员数量 DESC",
                ["personnel"],
            )
        )

    for question, sql, datasource_ids in seeds[:6]:
        try:
            result = await engine.run_sql(sql=sql, datasource_ids=datasource_ids, question=question)
            if not result.get("success"):
                continue
            result_id = store.save_result(request, result)
            store.pin(request, result_id)
        except Exception:
            continue

    return {"success": True, "data": store.list_pins(request)}


@router.post("/demo/reset-db")
def reset_demo_db(request: Request):
    _current_user(request)
    settings = get_settings()
    path = Path(settings.demo_db_path)
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass

    ensure_demo_db(settings.demo_db_path)
    return {"success": True}


class DrilldownRequest(BaseModel):
    result_id: str
    field: str
    value: str
    datasource_ids: list[str] = Field(default_factory=list)


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@router.post("/drilldown")
async def drilldown(request: Request, payload: DrilldownRequest):
    user = _current_user(request)
    base = store.get_result(request, payload.result_id)
    if not base:
        raise HTTPException(status_code=404, detail="找不到要下钻的结果")

    settings = get_settings()
    engine = QueryEngine(settings=settings)

    datasource_ids = payload.datasource_ids
    if not datasource_ids:
        ds = datasources(request)
        datasource_ids = [item["id"] for item in ds["data"]]
    else:
        datasource_ids = _filter_allowed_ids(user, datasource_ids)
        if not datasource_ids:
            raise HTTPException(status_code=403, detail="没有权限访问所选数据源")

    base_sql = (base.get("sql") or "").strip()
    m = re.search(r"\bFROM\b\s+([^\s,;]+)", base_sql, re.IGNORECASE)
    table = (m.group(1) if m else "").strip().strip('`"[]()').split(".")[-1]

    field = (payload.field or "").strip()
    value = (payload.value or "").strip()
    if not field or not value:
        raise HTTPException(status_code=400, detail="下钻参数不完整")

    sql = ""
    qv = _sql_quote(value)

    if table.lower() == "fire_alarm_record":
        base_select = (
            "SELECT unit_name AS 联网单位, device_name AS 设备名称, device_type AS 设备类型, "
            "alarm_location AS 报警位置, processing_state AS 处理状态, guard_name AS 值班人员, "
            "datetime(create_time/1000,'unixepoch','localtime') AS 报警时间 "
            "FROM fire_alarm_record "
        )
        if "月份" in field:
            sql = (
                base_select
                + "WHERE strftime('%Y-%m', datetime(create_time/1000,'unixepoch','localtime')) = "
                + qv
                + " ORDER BY create_time DESC LIMIT 200"
            )
        elif "联网单位" in field or field in {"单位", "单位名称"}:
            sql = base_select + f"WHERE unit_name = {qv} ORDER BY create_time DESC LIMIT 200"
        elif "报警位置" in field or field in {"位置", "地点"}:
            sql = base_select + f"WHERE alarm_location = {qv} ORDER BY create_time DESC LIMIT 200"
        elif "处理状态" in field or field in {"状态"}:
            sql = base_select + f"WHERE processing_state = {qv} ORDER BY create_time DESC LIMIT 200"

    elif table.lower() == "fire_equipment":
        base_select = (
            "SELECT station AS 站点, category AS 装备类别, equipment_name AS 装备名称, "
            "quantity AS 数量, status AS 状态 "
            "FROM fire_equipment "
        )
        if "站点" in field:
            sql = base_select + f"WHERE station = {qv} ORDER BY quantity DESC LIMIT 200"
        elif "装备类别" in field or "类别" in field:
            sql = base_select + f"WHERE category = {qv} ORDER BY quantity DESC LIMIT 200"
        elif "状态" in field:
            sql = base_select + f"WHERE status = {qv} ORDER BY quantity DESC LIMIT 200"

    elif table.lower() == "fire_inspection":
        base_select = (
            "SELECT unit_name AS 单位, inspection_date AS 检查日期, result AS 结论, "
            "score AS 得分, issues_count AS 问题数 "
            "FROM fire_inspection "
        )
        if "单位" in field:
            sql = base_select + f"WHERE unit_name = {qv} ORDER BY inspection_date DESC LIMIT 200"
        elif "结论" in field:
            sql = base_select + f"WHERE result = {qv} ORDER BY inspection_date DESC LIMIT 200"

    elif table.lower() == "fire_personnel":
        base_select = (
            "SELECT name AS 姓名, station AS 站点, role AS 岗位, phone AS 电话 "
            "FROM fire_personnel "
        )
        if "站点" in field:
            sql = base_select + f"WHERE station = {qv} ORDER BY name LIMIT 200"
        elif "岗位" in field:
            sql = base_select + f"WHERE role = {qv} ORDER BY name LIMIT 200"

    if not sql:
        raise HTTPException(status_code=400, detail="该图表暂不支持自动下钻")

    result = await engine.run_sql(sql=sql, datasource_ids=datasource_ids, question=f"下钻：{field}={value}")
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "下钻失败"))

    result_id = store.save_result(request, result)
    result["result_id"] = result_id
    return result
