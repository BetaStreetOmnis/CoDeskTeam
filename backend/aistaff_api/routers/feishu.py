from __future__ import annotations

import asyncio
import json
import re
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..config import Settings
from ..db import fetchall, fetchone, open_db, row_to_dict, rows_to_dicts, utc_now_iso
from ..deps import CurrentUser, get_current_user, get_db, get_settings, require_team_admin
from ..project_utils import resolve_project_path
from ..services.agent_service import AgentService
from ..services.feishu_service import FeishuWebhookService


router = APIRouter(tags=["feishu"])

_AT_TAG_RE = re.compile(r"<at\b[^>]*>.*?</at>", re.IGNORECASE | re.DOTALL)


def _safe_text(value: object) -> str:
    return str(value or "").strip()


def _callback_url(settings: Settings, hook: str) -> str:
    path = f"/api/feishu/webhook/{hook}"
    base = (getattr(settings, "public_base_url", "") or "").strip().rstrip("/")
    return f"{base}{path}" if base else path


def _extract_text_content(raw: object) -> str:
    text = _safe_text(raw)
    if not text:
        return ""

    parsed_text = text
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed_text = _safe_text(parsed.get("text") or parsed.get("content") or "") or text
    except Exception:
        parsed_text = text

    parsed_text = _AT_TAG_RE.sub("", parsed_text)
    return " ".join(parsed_text.split()).strip()


def _normalize_event(payload: dict[str, Any]) -> dict[str, Any]:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
    sender_id_obj = sender.get("sender_id") if isinstance(sender.get("sender_id"), dict) else {}

    event_type = _safe_text(header.get("event_type") or payload.get("type") or event.get("type")).lower()
    message_type = _safe_text(message.get("message_type") or event.get("msg_type") or event.get("message_type")).lower()

    sender_type = _safe_text(sender.get("sender_type") or event.get("sender_type")).lower()

    sender_id = _safe_text(
        sender_id_obj.get("open_id")
        or sender_id_obj.get("user_id")
        or sender_id_obj.get("union_id")
        or event.get("open_id")
        or sender.get("open_id")
        or sender.get("id")
    )
    chat_id = _safe_text(message.get("chat_id") or event.get("chat_id") or event.get("open_chat_id"))
    content_raw = message.get("content") if message else event.get("content")
    text = _extract_text_content(content_raw if content_raw is not None else event.get("text"))

    return {
        "event_type": event_type,
        "message_type": message_type,
        "sender_type": sender_type,
        "sender_id": sender_id,
        "chat_id": chat_id,
        "text": text,
    }


def _verify_token(payload: dict[str, Any], expected: str) -> bool:
    token_expected = _safe_text(expected)
    if not token_expected:
        return True

    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    candidates = [
        _safe_text(payload.get("token")),
        _safe_text(header.get("token")),
        _safe_text(payload.get("verification_token")),
    ]
    candidates = [c for c in candidates if c]
    if not candidates:
        return False
    return token_expected in candidates


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
    for skill in skills:
        name = _safe_text(skill.get("name"))
        desc = _safe_text(skill.get("description"))
        content = _safe_text(skill.get("content"))
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
    ws = _safe_text((row_to_dict(ws_row) or {}).get("workspace_path"))
    if ws:
        try:
            workspace_root = resolve_project_path(settings, ws)
        except Exception:
            workspace_root = settings.workspace_root
    return workspace_root


async def _process_feishu_text_message(*, settings: Settings, config: dict[str, Any], event: dict[str, Any]) -> None:
    team_id = int(config["team_id"])
    sender_id = _safe_text(event.get("sender_id"))
    chat_id = _safe_text(event.get("chat_id")) or None
    text = _safe_text(event.get("text"))
    if not sender_id or not text:
        return

    session_id = f"feishu:{config['hook']}:" + (f"chat:{chat_id}" if chat_id else f"user:{sender_id}")

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

    assistant = _safe_text((result or {}).get("assistant"))
    if not assistant:
        return

    webhook_url = _safe_text(config.get("webhook_url"))
    if not webhook_url:
        return

    svc = FeishuWebhookService()
    try:
        await svc.send_text(webhook_url=webhook_url, content=assistant)
    except Exception:
        # Best-effort: callback already acked.
        return


async def _get_feishu_config_by_hook(db, hook: str) -> dict[str, Any] | None:  # noqa: ANN001
    row = await fetchone(
        db,
        """
        SELECT id, team_id, name, hook, webhook_url, verification_token, enabled
        FROM feishu_webhooks
        WHERE hook = ?
        """,
        (_safe_text(hook),),
    )
    cfg = row_to_dict(row)
    if not cfg:
        return None
    cfg["enabled"] = bool(cfg.get("enabled"))
    return cfg


@router.post("/feishu/webhook/{hook}")
async def feishu_webhook_callback(
    hook: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),  # noqa: ANN001
) -> JSONResponse:
    cfg = await _get_feishu_config_by_hook(db, hook)
    if not cfg or not cfg.get("enabled"):
        raise HTTPException(status_code=404, detail="not found")

    body_bytes = await request.body()
    try:
        payload = json.loads(body_bytes.decode("utf-8", errors="replace"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json") from None

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")

    token_ok = _verify_token(payload, _safe_text(cfg.get("verification_token")))
    if not token_ok:
        raise HTTPException(status_code=403, detail="forbidden")

    challenge = _safe_text(payload.get("challenge"))
    if challenge:
        return JSONResponse(content={"challenge": challenge})

    event = _normalize_event(payload)
    is_text = event.get("message_type") == "text" or "im.message.receive" in _safe_text(event.get("event_type"))
    sender_type = _safe_text(event.get("sender_type")).lower()
    if sender_type in {"app", "bot"}:
        return JSONResponse(content={"code": 0})

    if is_text and _safe_text(event.get("text")):
        asyncio.create_task(_process_feishu_text_message(settings=settings, config=cfg, event=event))

    return JSONResponse(content={"code": 0})


class FeishuWebhook(BaseModel):
    id: int
    team_id: int
    name: str
    hook: str
    callback_url: str
    webhook_url: str
    verification_token: str | None
    enabled: bool
    created_at: str
    updated_at: str


class CreateFeishuWebhookRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    webhook_url: str = Field(min_length=8, max_length=500)
    verification_token: str | None = Field(default=None, max_length=200)
    enabled: bool = True


class UpdateFeishuWebhookRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    webhook_url: str | None = Field(default=None, min_length=8, max_length=500)
    verification_token: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None


def _feishu_model(settings: Settings, config: dict[str, Any]) -> FeishuWebhook:
    return FeishuWebhook(
        id=int(config["id"]),
        team_id=int(config["team_id"]),
        name=_safe_text(config.get("name")),
        hook=_safe_text(config.get("hook")),
        callback_url=_callback_url(settings, _safe_text(config.get("hook"))),
        webhook_url=_safe_text(config.get("webhook_url")),
        verification_token=_safe_text(config.get("verification_token")) or None,
        enabled=bool(config.get("enabled")),
        created_at=_safe_text(config.get("created_at")),
        updated_at=_safe_text(config.get("updated_at")),
    )


async def _create_unique_hook(db) -> str:  # noqa: ANN001
    for _ in range(20):
        candidate = secrets.token_hex(16)
        existing = await fetchone(db, "SELECT id FROM feishu_webhooks WHERE hook = ?", (candidate,))
        if not row_to_dict(existing):
            return candidate
    raise HTTPException(status_code=500, detail="生成回调 hook 失败")


def _feishu_preset_from_settings(settings: Settings) -> dict[str, Any] | None:
    webhook_url = _safe_text(getattr(settings, "feishu_preset_webhook_url", None))
    if not webhook_url:
        return None
    return {
        "name": _safe_text(getattr(settings, "feishu_preset_name", None)) or "飞书机器人（预配置）",
        "webhook_url": webhook_url,
        "verification_token": _safe_text(getattr(settings, "feishu_preset_verification_token", None)) or None,
        "enabled": bool(getattr(settings, "feishu_preset_enabled", True)),
    }


@router.get("/team/feishu/webhooks", response_model=list[FeishuWebhook])
async def list_feishu_webhooks(
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),  # noqa: ANN001
) -> list[FeishuWebhook]:
    require_team_admin(user)
    rows = await fetchall(
        db,
        """
        SELECT id, team_id, name, hook, webhook_url, verification_token, enabled, created_at, updated_at
        FROM feishu_webhooks
        WHERE team_id = ?
        ORDER BY id DESC
        """,
        (int(user.team_id),),
    )
    configs = rows_to_dicts(list(rows))
    for config in configs:
        config["enabled"] = bool(config.get("enabled"))
    return [_feishu_model(settings, config) for config in configs]


@router.post("/team/feishu/webhooks", response_model=FeishuWebhook)
async def create_feishu_webhook(
    req: CreateFeishuWebhookRequest,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),  # noqa: ANN001
) -> FeishuWebhook:
    require_team_admin(user)
    now = utc_now_iso()
    hook = await _create_unique_hook(db)

    cur = await db.execute(
        """
        INSERT INTO feishu_webhooks(team_id, name, hook, webhook_url, verification_token, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user.team_id),
            _safe_text(req.name),
            hook,
            _safe_text(req.webhook_url),
            _safe_text(req.verification_token) or None,
            1 if req.enabled else 0,
            now,
            now,
        ),
    )
    config_id = int(cur.lastrowid)
    await db.commit()

    row = await fetchone(
        db,
        """
        SELECT id, team_id, name, hook, webhook_url, verification_token, enabled, created_at, updated_at
        FROM feishu_webhooks
        WHERE id = ?
        """,
        (config_id,),
    )
    config = row_to_dict(row)
    if not config:
        raise HTTPException(status_code=500, detail="创建失败")
    config["enabled"] = bool(config.get("enabled"))
    return _feishu_model(settings, config)


@router.post("/team/feishu/webhooks/ensure-preset", response_model=FeishuWebhook)
async def ensure_feishu_webhook_preset(
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),  # noqa: ANN001
) -> FeishuWebhook:
    require_team_admin(user)

    preset = _feishu_preset_from_settings(settings)
    if not preset:
        raise HTTPException(
            status_code=400,
            detail="服务端未配置飞书预设，请先设置 AISTAFF_FEISHU_PRESET_WEBHOOK_URL",
        )

    now = utc_now_iso()
    existing_row = await fetchone(
        db,
        """
        SELECT id
        FROM feishu_webhooks
        WHERE team_id = ? AND webhook_url = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(user.team_id), _safe_text(preset.get("webhook_url"))),
    )
    existing = row_to_dict(existing_row)

    config_id: int
    if existing:
        config_id = int(existing.get("id"))
        await db.execute(
            """
            UPDATE feishu_webhooks
            SET name = ?, verification_token = ?, enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                _safe_text(preset.get("name")),
                _safe_text(preset.get("verification_token")) or None,
                1 if bool(preset.get("enabled")) else 0,
                now,
                config_id,
            ),
        )
    else:
        hook = await _create_unique_hook(db)
        cur = await db.execute(
            """
            INSERT INTO feishu_webhooks(team_id, name, hook, webhook_url, verification_token, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(user.team_id),
                _safe_text(preset.get("name")),
                hook,
                _safe_text(preset.get("webhook_url")),
                _safe_text(preset.get("verification_token")) or None,
                1 if bool(preset.get("enabled")) else 0,
                now,
                now,
            ),
        )
        config_id = int(cur.lastrowid)

    await db.commit()
    row = await fetchone(
        db,
        """
        SELECT id, team_id, name, hook, webhook_url, verification_token, enabled, created_at, updated_at
        FROM feishu_webhooks
        WHERE id = ?
        """,
        (config_id,),
    )
    config = row_to_dict(row)
    if not config:
        raise HTTPException(status_code=500, detail="导入飞书预配置失败")
    config["enabled"] = bool(config.get("enabled"))
    return _feishu_model(settings, config)


@router.put("/team/feishu/webhooks/{config_id}", response_model=FeishuWebhook)
async def update_feishu_webhook(
    config_id: int,
    req: UpdateFeishuWebhookRequest,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),  # noqa: ANN001
) -> FeishuWebhook:
    require_team_admin(user)
    existing_row = await fetchone(db, "SELECT id, team_id FROM feishu_webhooks WHERE id = ?", (int(config_id),))
    existing = row_to_dict(existing_row)
    if not existing or int(existing.get("team_id") or 0) != user.team_id:
        raise HTTPException(status_code=404, detail="配置不存在")

    fields: list[str] = []
    values: list[Any] = []
    if req.name is not None:
        fields.append("name = ?")
        values.append(_safe_text(req.name))
    if req.webhook_url is not None:
        fields.append("webhook_url = ?")
        values.append(_safe_text(req.webhook_url))
    if req.verification_token is not None:
        fields.append("verification_token = ?")
        values.append(_safe_text(req.verification_token) or None)
    if req.enabled is not None:
        fields.append("enabled = ?")
        values.append(1 if req.enabled else 0)

    if fields:
        fields.append("updated_at = ?")
        values.append(utc_now_iso())
        values.append(int(config_id))
        await db.execute(f"UPDATE feishu_webhooks SET {', '.join(fields)} WHERE id = ?", tuple(values))
        await db.commit()

    row = await fetchone(
        db,
        """
        SELECT id, team_id, name, hook, webhook_url, verification_token, enabled, created_at, updated_at
        FROM feishu_webhooks
        WHERE id = ?
        """,
        (int(config_id),),
    )
    config = row_to_dict(row)
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    config["enabled"] = bool(config.get("enabled"))
    return _feishu_model(settings, config)


@router.delete("/team/feishu/webhooks/{config_id}")
async def delete_feishu_webhook(
    config_id: int,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    require_team_admin(user)
    existing_row = await fetchone(db, "SELECT id, team_id FROM feishu_webhooks WHERE id = ?", (int(config_id),))
    existing = row_to_dict(existing_row)
    if not existing or int(existing.get("team_id") or 0) != user.team_id:
        raise HTTPException(status_code=404, detail="配置不存在")

    await db.execute("DELETE FROM feishu_webhooks WHERE id = ?", (int(config_id),))
    await db.commit()
    return {"ok": True}
