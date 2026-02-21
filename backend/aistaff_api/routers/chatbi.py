from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import Settings
from ..deps import CurrentUser, get_current_user, get_db, get_settings, require_team_admin
from ..services.chatbi.demo_db import ensure_demo_db
from ..services.chatbi.datasource_store import (
    delete_team_source,
    list_team_sources,
    upsert_team_source,
)
from ..services.chatbi.query_engine import ChatbiSettings, QueryEngine


router = APIRouter(tags=["chatbi"])


def _sse_pack(event: str, payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


def _chatbi_settings(settings: Settings) -> ChatbiSettings:
    demo_db_path = str((settings.db_path.parent / "chatbi_demo.db").resolve())
    model = (os.getenv("AISTAFF_CHATBI_MODEL") or "").strip() or settings.model
    llm_timeout_ms = int((os.getenv("AISTAFF_CHATBI_LLM_TIMEOUT_MS") or "45000").strip() or "45000")
    llm_explain_timeout_ms = int((os.getenv("AISTAFF_CHATBI_EXPLAIN_TIMEOUT_MS") or "12000").strip() or "12000")
    sql_max_rows = int((os.getenv("AISTAFF_CHATBI_SQL_MAX_ROWS") or "500").strip() or "500")
    sql_timeout_ms = int((os.getenv("AISTAFF_CHATBI_SQL_TIMEOUT_MS") or "8000").strip() or "8000")
    stream_chunk_chars = int((os.getenv("AISTAFF_CHATBI_STREAM_CHUNK_CHARS") or "48").strip() or "48")
    stream_chunk_delay_ms = int((os.getenv("AISTAFF_CHATBI_STREAM_CHUNK_DELAY_MS") or "0").strip() or "0")
    federated_max_rows_per_table = int(
        (os.getenv("AISTAFF_CHATBI_FEDERATED_MAX_ROWS_PER_TABLE") or "5000").strip() or "5000"
    )
    federated_batch_size = int((os.getenv("AISTAFF_CHATBI_FEDERATED_BATCH_SIZE") or "400").strip() or "400")

    return ChatbiSettings(
        demo_db_path=demo_db_path,
        openai_base_url=settings.openai_base_url,
        openai_api_key=settings.openai_api_key,
        model=model,
        llm_timeout_ms=max(1000, llm_timeout_ms),
        llm_explain_timeout_ms=max(1000, llm_explain_timeout_ms),
        sql_max_rows=max(1, sql_max_rows),
        sql_timeout_ms=max(0, sql_timeout_ms),
        stream_chunk_chars=max(1, stream_chunk_chars),
        stream_chunk_delay_ms=max(0, stream_chunk_delay_ms),
        federated_max_rows_per_table=max(0, federated_max_rows_per_table),
        federated_batch_size=max(1, federated_batch_size),
    )


class DatasourceResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    db_type: str = "sqlite"
    tables: list[str] = Field(default_factory=list)
    enabled: bool = True
    is_default: bool = False


@router.get("/chatbi/datasources")
async def list_datasources(
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    cfg = _chatbi_settings(settings)
    ensure_demo_db(cfg.demo_db_path)
    if not cfg.openai_api_key:
        raise HTTPException(status_code=400, detail="ChatBI 需要配置 OPENAI_API_KEY 才能生成 SQL")

    sources = await list_team_sources(db, team_id=user.team_id, demo_db_path=cfg.demo_db_path)
    data = [
        DatasourceResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            db_type=s.db_type,
            tables=list(s.tables),
            enabled=bool(s.enabled),
            is_default=bool(s.is_default),
        ).model_dump()
        for s in sources
    ]
    return {"success": True, "data": data}


class DatasourceUpsertRequest(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    db_type: str | None = None
    db_path: str | None = None
    db_url: str | None = None
    tables: list[str] = Field(default_factory=list)
    enabled: bool | None = None


@router.post("/chatbi/datasources")
async def upsert_datasource(
    payload: DatasourceUpsertRequest,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    require_team_admin(user)
    cfg = _chatbi_settings(settings)
    ensure_demo_db(cfg.demo_db_path)
    if not cfg.openai_api_key:
        raise HTTPException(status_code=400, detail="ChatBI 需要配置 OPENAI_API_KEY 才能生成 SQL")

    try:
        rec = await upsert_team_source(
            db,
            team_id=user.team_id,
            demo_db_path=cfg.demo_db_path,
            source=payload.model_dump(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "success": True,
        "data": DatasourceResponse(
            id=rec.id,
            name=rec.name,
            description=rec.description,
            db_type=rec.db_type,
            tables=list(rec.tables),
            enabled=bool(rec.enabled),
            is_default=bool(rec.is_default),
        ).model_dump(),
    }


@router.delete("/chatbi/datasources/{source_id}")
async def remove_datasource(
    source_id: str,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    require_team_admin(user)
    cfg = _chatbi_settings(settings)
    ensure_demo_db(cfg.demo_db_path)

    try:
        deleted = await delete_team_source(db, team_id=user.team_id, source_id=source_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not deleted:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return {"success": True}


class ChatRequest(BaseModel):
    question: str | None = None
    query: str | None = None
    datasource_ids: list[str] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)


@router.post("/chatbi/chat")
async def chat(
    payload: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    question = (payload.question or payload.query or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    cfg = _chatbi_settings(settings)
    ensure_demo_db(cfg.demo_db_path)

    sources = await list_team_sources(db, team_id=user.team_id, demo_db_path=cfg.demo_db_path)
    engine = QueryEngine(settings=cfg, datasources=sources)

    datasource_ids = payload.datasource_ids
    if not datasource_ids:
        datasource_ids = [s.id for s in sources if s.enabled]
    result = await engine.ask(question=question, datasource_ids=datasource_ids, history=payload.history)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=str(result.get("error") or "查询失败"))
    return result


@router.post("/chatbi/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> StreamingResponse:
    question = (payload.question or payload.query or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    cfg = _chatbi_settings(settings)
    ensure_demo_db(cfg.demo_db_path)

    sources = await list_team_sources(db, team_id=user.team_id, demo_db_path=cfg.demo_db_path)
    engine = QueryEngine(settings=cfg, datasources=sources)

    datasource_ids = payload.datasource_ids
    if not datasource_ids:
        datasource_ids = [s.id for s in sources if s.enabled]

    async def _stream():
        try:
            async for item in engine.ask_stream(
                question=question,
                datasource_ids=datasource_ids,
                history=payload.history,
            ):
                kind = item.get("type")
                if kind == "chat":
                    yield _sse_pack("chat", {"success": True, "mode": "chat", "reply": item.get("reply", ""), "question": question})
                elif kind == "sql_delta":
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
                    yield _sse_pack("result", {"result": item.get("result") or {}})
                elif kind == "error":
                    yield _sse_pack("error", {"error": item.get("error", "查询失败")})
        finally:
            yield _sse_pack("done", {"success": True})

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(_stream(), media_type="text/event-stream", headers=headers)


class SQLRunRequest(BaseModel):
    sql: str
    datasource_ids: list[str] = Field(default_factory=list)
    question: str | None = None


@router.post("/chatbi/sql/run")
async def run_sql(
    payload: SQLRunRequest,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    cfg = _chatbi_settings(settings)
    ensure_demo_db(cfg.demo_db_path)
    sources = await list_team_sources(db, team_id=user.team_id, demo_db_path=cfg.demo_db_path)
    engine = QueryEngine(settings=cfg, datasources=sources)

    datasource_ids = payload.datasource_ids
    if not datasource_ids:
        datasource_ids = [s.id for s in sources if s.enabled]

    result = await engine.run_sql(sql=payload.sql, datasource_ids=datasource_ids, question=payload.question)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=str(result.get("error") or "执行失败"))
    return result
