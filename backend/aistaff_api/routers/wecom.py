from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
from typing import Any
import re
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..agent.types import ChatMessage
from ..config import Settings
from ..db import fetchall, fetchone, open_db, row_to_dict, rows_to_dicts, utc_now_iso
from ..deps import CurrentUser, get_current_user, get_db, get_settings, require_team_admin
from ..project_utils import resolve_project_path, resolve_user_workspace_root
from ..services.agent_service import AgentService
from ..services.auth_service import hash_password
from ..services.history_file_store import sync_session_snapshot_from_db
from ..services.team_skill_seed_service import ensure_default_team_skills
from ..services.wecom_crypto import WecomCrypto
from ..services.wecom_service import WecomService
from ..session_store import get_session_store
from ..url_utils import abs_url


router = APIRouter(tags=["wecom"])

_FILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_IMAGE_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_MAX_MEDIA_BYTES = 25 * 1024 * 1024


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
        "media_id": g("MediaId"),
        "thumb_media_id": g("ThumbMediaId"),
        "pic_url": g("PicUrl"),
        "file_name": g("FileName"),
        "title": g("Title"),
        "format": g("Format"),
    }


def _callback_url(settings: Settings, hook: str) -> str:
    path = f"/api/wecom/callback/{hook}"
    base = (getattr(settings, "public_base_url", "") or "").strip().rstrip("/")
    return f"{base}{path}" if base else path


def _external_email(*, team_id: int, provider: str, external_id: str) -> str:
    raw = f"{provider}:{team_id}:{external_id}".encode("utf-8", errors="ignore")
    digest = hashlib.sha256(raw).digest()
    short = base64.b32encode(digest).decode("ascii").rstrip("=").lower()[:16]
    return f"ext+{provider}+t{int(team_id)}+{short}@aistaff.local"


def _safe_outputs_path(outputs_dir: Path, file_id: str) -> Path:
    file_id = (file_id or "").strip()
    if not file_id:
        raise ValueError("invalid file_id")
    if not _FILE_ID_RE.match(file_id) or ".." in file_id:
        raise ValueError("invalid file_id")

    base = outputs_dir.resolve()
    full = (base / file_id).resolve()
    if full == base or not str(full).startswith(str(base) + os.sep):
        raise ValueError("invalid file_id")
    return full


def _safe_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower() if filename else ""
    if not ext:
        return ""
    safe = "".join(ch for ch in ext if ch.isalnum() or ch in {".", "_", "-"})
    if not safe.startswith("."):
        return ""
    if safe in {"."}:
        return ""
    return safe[:16] if len(safe) > 16 else safe


def _safe_load_attachments(value: object) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except Exception:
            return []
        return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
    return []


def _extract_tool_files(events: list[dict]) -> list[dict]:
    out: list[dict] = []
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        if str(ev.get("type") or "") != "tool_result":
            continue
        result = ev.get("result") if isinstance(ev.get("result"), dict) else {}
        fid = str(result.get("file_id") or "").strip()
        if not fid:
            continue
        filename = str(result.get("filename") or fid).strip() or fid
        ctype = str(result.get("content_type") or "").strip().lower()
        out.append(
            {
                "file_id": fid,
                "filename": filename,
                "content_type": ctype,
                "kind": "generated",
            }
        )
    return out


def _extract_artifact_links(events: list[dict], settings: Settings) -> list[dict[str, str]]:
    """
    Extract download/preview links from tool events, so chat apps (WeCom/Feishu) can behave
    closer to the web UI even if the model forgets to paste the link.
    """

    items = events or []
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    for ev in items:
        if not isinstance(ev, dict):
            continue
        if str(ev.get("type") or "") != "tool_result":
            continue

        tool = str(ev.get("tool") or "").strip()
        result = ev.get("result") if isinstance(ev.get("result"), dict) else {}

        file_id = str(result.get("file_id") or "").strip()
        filename = str(result.get("filename") or file_id or tool or "").strip()

        download_url = str(result.get("download_url") or "").strip()
        if download_url:
            url = abs_url(settings, download_url)
            if url and url not in seen:
                out.append({"kind": "download", "label": filename or tool or "文件", "url": url})
                seen.add(url)

        preview_url = str(result.get("preview_url") or "").strip()
        if preview_url:
            url = abs_url(settings, preview_url)
            if url and url not in seen:
                out.append({"kind": "preview", "label": "预览", "url": url})
                seen.add(url)

        preview_image_url = str(result.get("preview_image_url") or "").strip()
        if preview_image_url:
            url = abs_url(settings, preview_image_url)
            if url and url not in seen:
                out.append({"kind": "preview_image", "label": "封面预览", "url": url})
                seen.add(url)

    return out


def _decorate_assistant_text(*, assistant: str, events: list[dict], settings: Settings) -> str:
    text = (assistant or "").strip()
    links = _extract_artifact_links(events, settings)
    if not links:
        return text

    # Avoid duplicating URLs if the model already included them.
    links = [link for link in links if link.get("url") and link["url"] not in text]
    if not links:
        return text

    download_lines: list[str] = []
    preview_lines: list[str] = []
    for link in links:
        kind = str(link.get("kind") or "").strip()
        label = str(link.get("label") or "").strip() or "链接"
        url = str(link.get("url") or "").strip()
        if not url:
            continue
        if kind == "download":
            download_lines.append(f"- {label}：{url}")
        else:
            preview_lines.append(f"- {label}：{url}")

    parts: list[str] = [text] if text else []
    if download_lines:
        parts.append("生成文件：\n" + "\n".join(download_lines))
    if preview_lines:
        parts.append("预览：\n" + "\n".join(preview_lines))
    return "\n\n".join([p for p in parts if p]).strip()


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


async def _get_or_create_wecom_user(
    *,
    db: object,
    team_id: int,
    external_id: str,
    display_name: str | None,
) -> dict[str, object]:
    provider = "wecom"
    ext = (external_id or "").strip()
    if not ext:
        raise ValueError("external_id is empty")

    now = utc_now_iso()
    disp = (display_name or "").strip() or ext

    mapping_row = await fetchone(
        db,
        """
        SELECT user_id
        FROM external_identities
        WHERE team_id = ? AND provider = ? AND external_id = ?
        """,
        (int(team_id), provider, ext),
    )
    mapping = row_to_dict(mapping_row) or {}
    mapped_user_id = int(mapping.get("user_id") or 0)

    if mapped_user_id > 0:
        user_row = await fetchone(db, "SELECT id, email, name FROM users WHERE id = ?", (mapped_user_id,))
        user = row_to_dict(user_row) or {}
        if user:
            await db.execute(
                "UPDATE external_identities SET display_name = ?, updated_at = ? WHERE team_id = ? AND provider = ? AND external_id = ?",
                (disp, now, int(team_id), provider, ext),
            )
            await db.commit()
            return {"id": int(user["id"]), "email": str(user.get("email") or ""), "name": str(user.get("name") or disp)}

        # Broken mapping; clear and recreate.
        await db.execute(
            "DELETE FROM external_identities WHERE team_id = ? AND provider = ? AND external_id = ?",
            (int(team_id), provider, ext),
        )
        await db.commit()

    email = _external_email(team_id=int(team_id), provider=provider, external_id=ext)
    pwd_hash = hash_password(secrets.token_urlsafe(32))

    await db.execute(
        "INSERT OR IGNORE INTO users(email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (email, disp, pwd_hash, now),
    )
    user_row = await fetchone(db, "SELECT id, email, name FROM users WHERE email = ?", (email,))
    user = row_to_dict(user_row) or {}
    if not user:
        raise RuntimeError("failed to create external user")

    user_id = int(user["id"])
    await db.execute(
        "INSERT OR IGNORE INTO memberships(user_id, team_id, role, created_at) VALUES (?, ?, ?, ?)",
        (user_id, int(team_id), "member", now),
    )
    await db.execute(
        """
        INSERT OR IGNORE INTO external_identities(team_id, provider, external_id, user_id, display_name, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (int(team_id), provider, ext, user_id, disp, now, now),
    )
    await db.commit()
    return {"id": user_id, "email": str(user.get("email") or ""), "name": str(user.get("name") or disp)}


async def _process_wecom_message(*, settings: Settings, app: dict[str, Any], message: dict[str, str]) -> None:
    team_id = int(app["team_id"])
    corp_id = _safe_text(app.get("corp_id"))
    from_user = _safe_text(message.get("from_user"))
    chat_id = _safe_text(message.get("chat_id")) or None
    msg_type = _safe_text(message.get("msg_type")).lower()
    raw_text = _safe_text(message.get("content"))
    media_id = _safe_text(message.get("media_id"))
    file_name = _safe_text(message.get("file_name")) or _safe_text(message.get("title"))

    if not from_user:
        return

    session_id = f"wecom:{app['hook']}:" + (f"chat:{chat_id}" if chat_id else f"user:{from_user}")
    msg_id = _safe_text(message.get("msg_id"))

    prefix = f"[{from_user}] " if chat_id else ""
    attachments: list[dict] = []
    text = ""
    if msg_type == "text":
        if not raw_text:
            return
        text = f"{prefix}{raw_text}"
    elif msg_type in {"image", "file"}:
        if not media_id:
            return
        display = file_name or ("图片" if msg_type == "image" else "文件")
        text = f"{prefix}发送了一个附件：{display}。请阅读附件并回答。"
    else:
        # Ignore other message types for now.
        return

    async with open_db(settings) as db:
        # Best-effort: dedup callbacks (WeCom may retry).
        if msg_id:
            try:
                event_id = f"{corp_id}:{msg_id}" if corp_id else msg_id
                now = utc_now_iso()
                cur = await db.execute(
                    """
                    INSERT OR IGNORE INTO external_events(team_id, provider, external_id, session_id, user_id, created_at)
                    VALUES (?, ?, ?, ?, NULL, ?)
                    """,
                    (team_id, "wecom", event_id, session_id, now),
                )
                inserted = bool(getattr(cur, "rowcount", 0) or 0)
                await cur.close()
                if not inserted:
                    return
                await db.commit()
            except Exception:
                pass

        # Best-effort: seed defaults for the team (doesn't affect prompts unless enabled).
        try:
            await ensure_default_team_skills(db, team_id=team_id)
        except Exception:
            pass

        team_prompt = await _build_team_prompt(db, team_id)

        team_row = await fetchone(db, "SELECT id, name FROM teams WHERE id = ?", (team_id,))
        team = row_to_dict(team_row) or {}
        team_name = str(team.get("name") or f"team-{team_id}")

        # Use per-user chat identity for group chats to avoid session ownership conflicts.
        if chat_id:
            external_id = f"{corp_id}:chat:{chat_id}" if corp_id else f"chat:{chat_id}"
            display = f"WeCom Chat {chat_id}"
        else:
            external_id = f"{corp_id}:user:{from_user}" if corp_id else f"user:{from_user}"
            display = from_user

        try:
            user_info = await _get_or_create_wecom_user(db=db, team_id=team_id, external_id=external_id, display_name=display)
        except Exception:
            return

        user_id = int(user_info.get("id") or 0)
        user_name = str(user_info.get("name") or "").strip() or display
        if user_id <= 0:
            return

        base_workspace = await _resolve_team_workspace(settings, db, team_id)
        try:
            workspace_root = resolve_user_workspace_root(
                settings,
                Path(base_workspace),
                team_id,
                user_id,
                team_name,
                user_name,
            )
        except Exception:
            workspace_root = Path(base_workspace)

        # Best-effort: rehydrate in-memory session from DB history (e.g. after server restart).
        try:
            store = get_session_store()
            ttl_seconds = max(0, int(settings.session_ttl_minutes)) * 60
            try:
                await store.assert_access(session_id=session_id, user_id=user_id, team_id=team_id, ttl_seconds=ttl_seconds)
            except Exception:
                sess_row = await fetchone(
                    db,
                    "SELECT session_id FROM chat_sessions WHERE session_id = ? AND team_id = ? AND user_id = ?",
                    (session_id, team_id, user_id),
                )
                if sess_row:
                    st = await store.get_or_create(
                        session_id=session_id,
                        user_id=user_id,
                        team_id=team_id,
                        role="general",
                        system_prompt="(rehydrated)",
                        workspace_root=str(workspace_root),
                        ttl_seconds=ttl_seconds,
                        max_sessions=max(0, int(settings.max_sessions)),
                    )
                    msg_rows = await fetchall(
                        db,
                        """
                        SELECT role, content, attachments_json
                        FROM chat_messages
                        WHERE session_id = ? AND team_id = ? AND user_id = ?
                        ORDER BY id ASC
                        """,
                        (session_id, team_id, user_id),
                    )
                    msgs: list[ChatMessage] = [ChatMessage(role="system", content=(st.messages[0].content if st.messages else ""))]
                    for r in msg_rows:
                        d = row_to_dict(r) or {}
                        role_name = str(d.get("role") or "").strip()
                        if role_name not in {"user", "assistant"}:
                            continue
                        atts = _safe_load_attachments(d.get("attachments_json"))
                        msgs.append(
                            ChatMessage(
                                role=role_name,  # type: ignore[arg-type]
                                content=str(d.get("content") or ""),
                                attachments=atts or None,
                            )
                        )
                    await store.update_messages(
                        session_id=session_id,
                        user_id=user_id,
                        team_id=team_id,
                        messages=msgs,
                        max_messages=max(0, int(settings.max_session_messages)),
                        max_chars=max(0, int(settings.max_context_chars)),
                    )
        except Exception:
            pass

    # Fetch media attachment (best-effort; avoid holding DB connection during download).
    if msg_type in {"image", "file"}:
        svc = WecomService()
        try:
            data, ctype, header_name = await svc.download_media(
                corp_id=str(app["corp_id"]),
                corp_secret=str(app["corp_secret"]),
                media_id=media_id,
            )
            if not data:
                raise ValueError("empty media")
            if len(data) > _MAX_MEDIA_BYTES:
                raise ValueError("media too large")

            filename_in = file_name or (header_name or "") or f"{msg_type}-{msg_id or media_id}"
            ext = _safe_ext(filename_in)
            if not ext and ctype in _IMAGE_EXT_BY_MIME:
                ext = _IMAGE_EXT_BY_MIME[ctype]

            file_id = f"{uuid4().hex}{ext}" if ext else uuid4().hex
            settings.outputs_dir.mkdir(parents=True, exist_ok=True)
            path = _safe_outputs_path(settings.outputs_dir, file_id)
            path.write_bytes(data)

            kind = "image" if ctype.startswith("image/") else "file"
            attachments = [
                {
                    "file_id": file_id,
                    "filename": filename_in or file_id,
                    "content_type": ctype,
                    "kind": kind,
                }
            ]
        except Exception:
            # If we can't fetch the media, inform user (best-effort) and stop.
            try:
                await svc.send_text(
                    corp_id=str(app["corp_id"]),
                    corp_secret=str(app["corp_secret"]),
                    agent_id=int(app["agent_id"]),
                    to_user=None if chat_id else from_user,
                    chat_id=chat_id,
                    content="附件获取失败（可能已过期或权限不足），请重新发送或稍后再试。",
                )
            except Exception:
                pass
            return

    agent = AgentService(settings)
    result = await agent.chat(
        message=text,
        session_id=session_id,
        role="general",
        user_id=user_id,
        team_id=team_id,
        provider=None,
        model=None,
        workspace_root=workspace_root,
        security_preset=None,
        enable_shell=None,
        enable_write=None,
        enable_browser=None,
        show_reasoning=None,
        attachments=attachments,
        team_skills_prompt=team_prompt or None,
    )

    events = list((result or {}).get("events") or [])
    assistant = _decorate_assistant_text(assistant=str((result or {}).get("assistant") or ""), events=events, settings=settings)
    if not assistant:
        return

    # Persist session + messages (best-effort).
    try:
        now = utc_now_iso()
        provider_name = (settings.provider or "openai").strip().lower()
        model_name = (settings.model or "").strip()
        title = f"[wecom] {'chat ' + chat_id if chat_id else from_user}".strip()

        async with open_db(settings) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO chat_sessions(
                  session_id, team_id, user_id, role, provider, model, project_id, title, opencode_session_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    team_id,
                    user_id,
                    "general",
                    provider_name,
                    model_name,
                    title,
                    result.get("opencode_session_id"),
                    now,
                    now,
                ),
            )
            await db.execute(
                """
                UPDATE chat_sessions
                SET updated_at = ?,
                    role = ?,
                    provider = ?,
                    model = ?,
                    opencode_session_id = COALESCE(opencode_session_id, ?),
                    title = CASE WHEN title = '' THEN ? ELSE title END
                WHERE session_id = ? AND team_id = ? AND user_id = ?
                """,
                (
                    now,
                    "general",
                    provider_name,
                    model_name,
                    result.get("opencode_session_id"),
                    title,
                    session_id,
                    team_id,
                    user_id,
                ),
            )

            await db.execute(
                """
                INSERT INTO chat_messages(session_id, team_id, user_id, role, content, attachments_json, events_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    session_id,
                    team_id,
                    user_id,
                    "user",
                    text,
                    json.dumps(attachments or [], ensure_ascii=False),
                    now,
                ),
            )
            await db.execute(
                """
                INSERT INTO chat_messages(session_id, team_id, user_id, role, content, attachments_json, events_json, created_at)
                VALUES (?, ?, ?, ?, ?, '[]', ?, ?)
                """,
                (
                    session_id,
                    team_id,
                    user_id,
                    "assistant",
                    assistant,
                    json.dumps(events, ensure_ascii=False),
                    now,
                ),
            )

            # Index user attachments + tool-generated files (best-effort).
            files_to_index: list[dict] = []
            for a in attachments or []:
                if not isinstance(a, dict):
                    continue
                fid = str(a.get("file_id") or "").strip()
                if not fid:
                    continue
                files_to_index.append(
                    {
                        "file_id": fid,
                        "filename": str(a.get("filename") or fid),
                        "content_type": str(a.get("content_type") or ""),
                        "kind": str(a.get("kind") or ("image" if str(a.get("content_type") or "").startswith("image/") else "file")),
                    }
                )
            files_to_index.extend(_extract_tool_files(events))

            for f in files_to_index:
                fid = str(f.get("file_id") or "").strip()
                if not fid:
                    continue
                try:
                    path = _safe_outputs_path(settings.outputs_dir, fid)
                    size_bytes = int(path.stat().st_size) if path.exists() and path.is_file() else 0
                except Exception:
                    size_bytes = 0
                filename = str(f.get("filename") or fid).strip() or fid
                ctype = str(f.get("content_type") or "").strip().lower() or "application/octet-stream"
                kind = str(f.get("kind") or "file").strip().lower()

                await db.execute(
                    """
                    INSERT OR IGNORE INTO file_records(
                      file_id, team_id, user_id, project_id, session_id, kind, filename, content_type, size_bytes, created_at
                    ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)
                    """,
                    (fid, team_id, user_id, session_id, kind, filename, ctype, size_bytes, now),
                )
                await db.execute(
                    """
                    UPDATE file_records
                    SET session_id = COALESCE(session_id, ?)
                    WHERE file_id = ? AND team_id = ? AND user_id = ?
                    """,
                    (session_id, fid, team_id, user_id),
                )

            await db.commit()

            try:
                await sync_session_snapshot_from_db(settings=settings, db=db, team_id=team_id, user_id=user_id, session_id=session_id)
            except Exception:
                pass
    except Exception:
        pass

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
    msg_type = _safe_text(msg.get("msg_type")).lower()
    is_text = msg_type == "text" and _safe_text(msg.get("content"))
    is_media = msg_type in {"image", "file"} and _safe_text(msg.get("media_id"))
    if is_text or is_media:
        asyncio.create_task(_process_wecom_message(settings=settings, app=app, message=msg))

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
