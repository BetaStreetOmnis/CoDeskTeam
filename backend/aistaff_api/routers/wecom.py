from __future__ import annotations

import asyncio
import secrets
from typing import Any
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..config import Settings
from ..db import fetchall, fetchone, open_db, row_to_dict, rows_to_dicts, utc_now_iso
from ..deps import CurrentUser, get_current_user, get_db, get_settings, require_team_admin
from ..project_utils import resolve_project_path
from ..services.agent_service import AgentService
from ..services.wecom_crypto import WecomCrypto
from ..services.wecom_service import WecomService


router = APIRouter(tags=["wecom"])


def _safe_text(value: object) -> str:
    return str(value or "").strip()


def _extract_encrypt(xml_text: str) -> str:
    try:
        root = ET.fromstring((xml_text or "").encode("utf-8", errors="replace"))
    except Exception as e:
        raise ValueError(f"invalid xml: {e}") from None
    enc = root.findtext("Encrypt") or root.findtext("./Encrypt") or ""
    enc = str(enc or "").strip()
    if not enc:
        raise ValueError("missing Encrypt")
    return enc


def _parse_plain_message(xml_text: str) -> dict[str, str]:
    try:
        root = ET.fromstring((xml_text or "").encode("utf-8", errors="replace"))
    except Exception as e:
        raise ValueError(f"invalid decrypted xml: {e}") from None

    def g(tag: str) -> str:
        return _safe_text(root.findtext(tag))

    return {
        "to_user": g("ToUserName"),
        "from_user": g("FromUserName"),
        "create_time": g("CreateTime"),
        "msg_type": g("MsgType").lower(),
        "content": g("Content"),
        "msg_id": g("MsgId"),
        "agent_id": g("AgentID"),
        "chat_id": g("ChatId"),
        "event": g("Event"),
        "event_key": g("EventKey"),
    }


def _callback_url(settings: Settings, hook: str) -> str:
    path = f"/api/wecom/callback/{hook}"
    base = (getattr(settings, "public_base_url", "") or "").strip().rstrip("/")
    return f"{base}{path}" if base else path


async def _build_team_prompt(db, team_id: int) -> str:  # noqa: ANN001
    rows = await fetchall(
        db,
        """
        SELECT name, description, content
        FROM team_skills
        WHERE team_id = ? AND enabled = 1
        ORDER BY id DESC
        """,
        (int(team_id),),
    )
    skills = rows_to_dicts(list(rows))
    if not skills:
        return ""

    parts: list[str] = ["你所在团队配置了以下“团队技能/规范”。在回答与执行任务时必须遵守，并在合适时主动应用："]
    for s in skills:
        name = str(s.get("name") or "").strip()
        desc = str(s.get("description") or "").strip()
        content = str(s.get("content") or "").strip()
        if not name and not content:
            continue
        parts.append(f"### {name or '未命名技能'}")
        if desc:
            parts.append(f"说明：{desc}")
        if content:
            parts.append(content)
    return "\n\n".join(parts).strip()


async def _resolve_team_workspace(settings: Settings, db, team_id: int):  # noqa: ANN001
    workspace_root = settings.workspace_root
    ws_row = await fetchone(db, "SELECT workspace_path FROM team_settings WHERE team_id = ?", (int(team_id),))
    ws = str((row_to_dict(ws_row) or {}).get("workspace_path") or "").strip()
    if ws:
        try:
            workspace_root = resolve_project_path(settings, ws)
        except Exception:
            workspace_root = settings.workspace_root
    return workspace_root


async def _process_wecom_text_message(*, settings: Settings, app: dict[str, Any], message: dict[str, str]) -> None:
    team_id = int(app["team_id"])
    from_user = _safe_text(message.get("from_user"))
    chat_id = _safe_text(message.get("chat_id")) or None
    text = _safe_text(message.get("content"))
    if not from_user or not text:
        return

    session_id = f"wecom:{app['hook']}:" + (f"chat:{chat_id}" if chat_id else f"user:{from_user}")

    async with open_db(settings) as db:
        team_prompt = await _build_team_prompt(db, team_id)
        workspace_root = await _resolve_team_workspace(settings, db, team_id)

    agent = AgentService(settings)
    result = await agent.chat(
        message=text,
        session_id=session_id,
        role="general",
        user_id=0,
        team_id=team_id,
        provider=None,
        model=None,
        workspace_root=workspace_root,
        security_preset=None,
        enable_shell=None,
        enable_write=None,
        enable_browser=None,
        show_reasoning=None,
        attachments=[],
        team_skills_prompt=team_prompt or None,
    )

    assistant = str((result or {}).get("assistant") or "").strip()
    if not assistant:
        return

    svc = WecomService()
    try:
        await svc.send_text(
            corp_id=str(app["corp_id"]),
            corp_secret=str(app["corp_secret"]),
            agent_id=int(app["agent_id"]),
            to_user=None if chat_id else from_user,
            chat_id=chat_id,
            content=assistant,
        )
    except Exception:
        # Best-effort: callback already acked.
        return


async def _get_wecom_app_by_hook(db, hook: str) -> dict[str, Any] | None:  # noqa: ANN001
    row = await fetchone(
        db,
        """
        SELECT id, team_id, name, hook, corp_id, agent_id, corp_secret, token, encoding_aes_key, enabled
        FROM wecom_apps
        WHERE hook = ?
        """,
        (_safe_text(hook),),
    )
    app = row_to_dict(row)
    if not app:
        return None
    app["enabled"] = bool(app.get("enabled"))
    return app


@router.get("/wecom/callback/{hook}")
async def wecom_verify_url(
    hook: str,
    msg_signature: str = Query(min_length=1, alias="msg_signature"),
    timestamp: str = Query(min_length=1),
    nonce: str = Query(min_length=1),
    echostr: str = Query(min_length=1),
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),  # noqa: ANN001
) -> Response:
    app = await _get_wecom_app_by_hook(db, hook)
    if not app or not app.get("enabled"):
        raise HTTPException(status_code=404, detail="wecom app not found")

    crypto = WecomCrypto(token=str(app["token"]), encoding_aes_key=str(app["encoding_aes_key"]), corp_id=str(app["corp_id"]))
    try:
        plain = crypto.decrypt(msg_signature=msg_signature, timestamp=timestamp, nonce=nonce, encrypted=echostr)
    except ValueError:
        raise HTTPException(status_code=403, detail="forbidden") from None

    return Response(content=plain, media_type="text/plain")


@router.post("/wecom/callback/{hook}")
async def wecom_callback(
    hook: str,
    request: Request,
    msg_signature: str = Query(min_length=1, alias="msg_signature"),
    timestamp: str = Query(min_length=1),
    nonce: str = Query(min_length=1),
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),  # noqa: ANN001
) -> Response:
    app = await _get_wecom_app_by_hook(db, hook)
    if not app or not app.get("enabled"):
        # For callbacks, keep response minimal.
        raise HTTPException(status_code=404, detail="not found")

    body = (await request.body()).decode("utf-8", errors="replace")
    try:
        encrypted = _extract_encrypt(body)
        crypto = WecomCrypto(token=str(app["token"]), encoding_aes_key=str(app["encoding_aes_key"]), corp_id=str(app["corp_id"]))
        plain_xml = crypto.decrypt(msg_signature=msg_signature, timestamp=timestamp, nonce=nonce, encrypted=encrypted)
        msg = _parse_plain_message(plain_xml)
    except ValueError:
        raise HTTPException(status_code=403, detail="forbidden") from None

    # Ack ASAP to prevent retries; process in background.
    if msg.get("msg_type") == "text" and _safe_text(msg.get("content")):
        asyncio.create_task(_process_wecom_text_message(settings=settings, app=app, message=msg))

    return Response(content="success", media_type="text/plain")


class WecomApp(BaseModel):
    id: int
    team_id: int
    name: str
    hook: str
    callback_url: str
    corp_id: str
    agent_id: int
    corp_secret: str
    token: str
    encoding_aes_key: str
    enabled: bool
    created_at: str
    updated_at: str


class CreateWecomAppRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    corp_id: str = Field(min_length=1, max_length=120)
    agent_id: int = Field(ge=1)
    corp_secret: str = Field(min_length=1, max_length=300)
    token: str = Field(min_length=1, max_length=100)
    encoding_aes_key: str = Field(min_length=10, max_length=200)
    enabled: bool = True


class UpdateWecomAppRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    corp_id: str | None = Field(default=None, min_length=1, max_length=120)
    agent_id: int | None = Field(default=None, ge=1)
    corp_secret: str | None = Field(default=None, min_length=1, max_length=300)
    token: str | None = Field(default=None, min_length=1, max_length=100)
    encoding_aes_key: str | None = Field(default=None, min_length=10, max_length=200)
    enabled: bool | None = None


def _wecom_app_model(settings: Settings, app: dict[str, Any]) -> WecomApp:
    return WecomApp(
        id=int(app["id"]),
        team_id=int(app["team_id"]),
        name=str(app.get("name") or ""),
        hook=str(app.get("hook") or ""),
        callback_url=_callback_url(settings, str(app.get("hook") or "")),
        corp_id=str(app.get("corp_id") or ""),
        agent_id=int(app.get("agent_id") or 0),
        corp_secret=str(app.get("corp_secret") or ""),
        token=str(app.get("token") or ""),
        encoding_aes_key=str(app.get("encoding_aes_key") or ""),
        enabled=bool(app.get("enabled")),
        created_at=str(app.get("created_at") or ""),
        updated_at=str(app.get("updated_at") or ""),
    )


@router.get("/team/wecom/apps", response_model=list[WecomApp])
async def list_wecom_apps(
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),  # noqa: ANN001
) -> list[WecomApp]:
    require_team_admin(user)
    rows = await fetchall(
        db,
        """
        SELECT id, team_id, name, hook, corp_id, agent_id, corp_secret, token, encoding_aes_key, enabled, created_at, updated_at
        FROM wecom_apps
        WHERE team_id = ?
        ORDER BY id DESC
        """,
        (int(user.team_id),),
    )
    apps = rows_to_dicts(list(rows))
    for a in apps:
        a["enabled"] = bool(a.get("enabled"))
    return [_wecom_app_model(settings, a) for a in apps]


@router.post("/team/wecom/apps", response_model=WecomApp)
async def create_wecom_app(
    req: CreateWecomAppRequest,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),  # noqa: ANN001
) -> WecomApp:
    require_team_admin(user)
    now = utc_now_iso()

    hook: str | None = None
    for _ in range(10):
        candidate = secrets.token_hex(16)
        existing = await fetchone(db, "SELECT id FROM wecom_apps WHERE hook = ?", (candidate,))
        if not row_to_dict(existing):
            hook = candidate
            break
    if not hook:
        raise HTTPException(status_code=500, detail="生成回调 hook 失败")

    cur = await db.execute(
        """
        INSERT INTO wecom_apps(team_id, name, hook, corp_id, agent_id, corp_secret, token, encoding_aes_key, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user.team_id),
            req.name.strip(),
            hook,
            req.corp_id.strip(),
            int(req.agent_id),
            req.corp_secret.strip(),
            req.token.strip(),
            req.encoding_aes_key.strip(),
            1 if req.enabled else 0,
            now,
            now,
        ),
    )
    app_id = int(cur.lastrowid)
    await db.commit()

    row = await fetchone(
        db,
        """
        SELECT id, team_id, name, hook, corp_id, agent_id, corp_secret, token, encoding_aes_key, enabled, created_at, updated_at
        FROM wecom_apps
        WHERE id = ?
        """,
        (app_id,),
    )
    app = row_to_dict(row)
    if not app:
        raise HTTPException(status_code=500, detail="创建失败")
    app["enabled"] = bool(app.get("enabled"))
    return _wecom_app_model(settings, app)


@router.put("/team/wecom/apps/{app_id}", response_model=WecomApp)
async def update_wecom_app(
    app_id: int,
    req: UpdateWecomAppRequest,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),  # noqa: ANN001
) -> WecomApp:
    require_team_admin(user)
    existing_row = await fetchone(db, "SELECT id, team_id FROM wecom_apps WHERE id = ?", (int(app_id),))
    existing = row_to_dict(existing_row)
    if not existing or int(existing.get("team_id") or 0) != user.team_id:
        raise HTTPException(status_code=404, detail="配置不存在")

    fields: list[str] = []
    values: list = []
    if req.name is not None:
        fields.append("name = ?")
        values.append(req.name.strip())
    if req.corp_id is not None:
        fields.append("corp_id = ?")
        values.append(req.corp_id.strip())
    if req.agent_id is not None:
        fields.append("agent_id = ?")
        values.append(int(req.agent_id))
    if req.corp_secret is not None:
        fields.append("corp_secret = ?")
        values.append(req.corp_secret.strip())
    if req.token is not None:
        fields.append("token = ?")
        values.append(req.token.strip())
    if req.encoding_aes_key is not None:
        fields.append("encoding_aes_key = ?")
        values.append(req.encoding_aes_key.strip())
    if req.enabled is not None:
        fields.append("enabled = ?")
        values.append(1 if req.enabled else 0)

    if fields:
        fields.append("updated_at = ?")
        values.append(utc_now_iso())
        values.append(int(app_id))
        await db.execute(f"UPDATE wecom_apps SET {', '.join(fields)} WHERE id = ?", tuple(values))
        await db.commit()

    row = await fetchone(
        db,
        """
        SELECT id, team_id, name, hook, corp_id, agent_id, corp_secret, token, encoding_aes_key, enabled, created_at, updated_at
        FROM wecom_apps
        WHERE id = ?
        """,
        (int(app_id),),
    )
    app = row_to_dict(row)
    if not app:
        raise HTTPException(status_code=404, detail="配置不存在")
    app["enabled"] = bool(app.get("enabled"))
    return _wecom_app_model(settings, app)


@router.delete("/team/wecom/apps/{app_id}")
async def delete_wecom_app(
    app_id: int,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    require_team_admin(user)
    existing_row = await fetchone(db, "SELECT id, team_id FROM wecom_apps WHERE id = ?", (int(app_id),))
    existing = row_to_dict(existing_row)
    if not existing or int(existing.get("team_id") or 0) != user.team_id:
        raise HTTPException(status_code=404, detail="配置不存在")
    await db.execute("DELETE FROM wecom_apps WHERE id = ?", (int(app_id),))
    await db.commit()
    return {"ok": True}
