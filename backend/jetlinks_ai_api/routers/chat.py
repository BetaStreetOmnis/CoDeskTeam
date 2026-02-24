from __future__ import annotations

import json
import os
from pathlib import Path
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..agent.types import ChatMessage
from ..db import fetchall, fetchone, row_to_dict, rows_to_dicts, utc_now_iso
from ..deps import CurrentUser, get_current_user, get_db, get_settings
from ..project_utils import resolve_project_path, resolve_user_workspace_root
from ..services.agent_service import AgentService
from ..services.team_skill_seed_service import ensure_default_team_skills
from ..services.history_file_store import sync_session_snapshot_from_db
from ..session_store import get_session_store


router = APIRouter(tags=["chat"])

_FILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


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


def _truncate_title(text: str, max_len: int = 48) -> str:
    t = (text or "").strip().replace("\n", " ").replace("\r", " ")
    t = " ".join(t.split())
    if len(t) <= max_len:
        return t
    return t[: max(0, max_len - 1)] + "…"


def _infer_kind(att: dict) -> str:
    kind = str(att.get("kind") or att.get("type") or "").strip().lower()
    if kind in {"image", "file"}:
        return kind
    ctype = str(att.get("content_type") or "").strip().lower()
    if ctype.startswith("image/"):
        return "image"
    fid = str(att.get("file_id") or "").lower()
    if fid.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image"
    return "file"


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
        result = ev.get("result")
        if not isinstance(result, dict):
            continue
        fid = str(result.get("file_id") or "").strip()
        if not fid:
            continue
        out.append(
            {
                "file_id": fid,
                "filename": str(result.get("filename") or fid),
                "content_type": str(result.get("content_type") or ""),
                "kind": "generated",
            }
        )
    return out


def _resolve_security_toggles(
    security_preset: str | None,
    enable_shell: bool | None,
    enable_write: bool | None,
    enable_browser: bool | None,
) -> tuple[bool, bool, bool]:
    preset = str(security_preset or "safe").strip().lower()
    if preset == "safe":
        return False, False, False
    if preset == "standard":
        return False, True, False
    if preset == "power":
        return True, True, True
    return bool(enable_shell), bool(enable_write), bool(enable_browser)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    role: str = "general"
    provider: str | None = None
    model: str | None = None
    project_id: int | None = None
    security_preset: str | None = None
    enable_shell: bool | None = None
    enable_write: bool | None = None
    enable_browser: bool | None = None
    enable_dangerous: bool | None = None
    show_reasoning: bool | None = None
    attachments: list[dict] = Field(default_factory=list)


class ChatResponse(BaseModel):
    session_id: str
    assistant: str
    events: list[dict]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> ChatResponse:
    service = AgentService(settings)

    try:
        requested_shell, requested_write, requested_browser = _resolve_security_toggles(
            req.security_preset,
            req.enable_shell,
            req.enable_write,
            req.enable_browser,
        )
        provider_name = (req.provider or settings.provider or "openai").lower()
        if user.team_role not in {"owner", "admin"} and any(
            [requested_shell, requested_write, requested_browser]
        ):
            raise HTTPException(status_code=403, detail="需要团队管理员权限启用高危工具（shell/write/browser）")
        if req.enable_dangerous and provider_name == "codex" and user.team_role not in {"owner", "admin"}:
            raise HTTPException(status_code=403, detail="需要团队管理员权限启用无沙箱模式（Codex）")

        # Guard: prevent reusing a persisted session_id owned by another user/team (can happen after server restart).
        if req.session_id:
            try:
                sess_row = await fetchone(db, "SELECT team_id, user_id FROM chat_sessions WHERE session_id = ?", (req.session_id,))
                sess = row_to_dict(sess_row) or {}
                if sess and (int(sess.get("team_id") or 0) != user.team_id or int(sess.get("user_id") or 0) != user.id):
                    req.session_id = None
            except Exception:
                pass

        workspace_root = settings.workspace_root
        if req.project_id is not None:
            proj_row = await fetchone(
                db,
                """
                SELECT id, team_id, path, enabled
                FROM team_projects
                WHERE id = ?
                """,
                (int(req.project_id),),
            )
            proj = row_to_dict(proj_row)
            if not proj or int(proj.get("team_id") or 0) != user.team_id:
                raise HTTPException(status_code=404, detail="项目不存在")
            if not bool(proj.get("enabled")):
                raise HTTPException(status_code=400, detail="项目已禁用")
            try:
                workspace_root = resolve_project_path(settings, str(proj.get("path") or ""))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"项目路径无效：{e}") from e
        else:
            ws_row = await fetchone(
                db,
                "SELECT workspace_path FROM team_settings WHERE team_id = ?",
                (user.team_id,),
            )
            ws = str((row_to_dict(ws_row) or {}).get("workspace_path") or "").strip()
            if ws:
                try:
                    workspace_root = resolve_project_path(settings, ws)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=f"团队工作区路径无效：{e}") from e
            try:
                workspace_root = resolve_user_workspace_root(
                    settings,
                    Path(workspace_root),
                    user.team_id,
                    user.id,
                    user.team_name,
                    user.name,
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"用户工作区路径无效：{e}") from e

        # Best-effort: seed defaults for the team (doesn't affect prompts unless enabled).
        try:
            await ensure_default_team_skills(db, team_id=user.team_id)
        except Exception:
            pass

        rows = await fetchall(
            db,
            """
            SELECT name, description, content
            FROM team_skills
            WHERE team_id = ? AND enabled = 1
            ORDER BY id DESC
            """,
            (user.team_id,),
        )
        skills = rows_to_dicts(list(rows))
        team_prompt = ""
        if skills:
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
            team_prompt = "\n\n".join(parts).strip()

        # Best-effort: rehydrate in-memory session from DB history (e.g. after server restart),
        # so continuing an existing session_id keeps context.
        if req.session_id:
            try:
                store = get_session_store()
                ttl_seconds = max(0, int(settings.session_ttl_minutes)) * 60
                try:
                    await store.assert_access(session_id=req.session_id, user_id=user.id, team_id=user.team_id, ttl_seconds=ttl_seconds)
                except Exception:
                    sess_row = await fetchone(
                        db,
                        "SELECT session_id FROM chat_sessions WHERE session_id = ? AND team_id = ? AND user_id = ?",
                        (req.session_id, user.team_id, user.id),
                    )
                    if sess_row:
                        workspace = (workspace_root or settings.workspace_root).resolve()
                        st = await store.get_or_create(
                            session_id=req.session_id,
                            user_id=user.id,
                            team_id=user.team_id,
                            role=req.role,
                            system_prompt="(rehydrated)",
                            workspace_root=str(workspace),
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
                            (req.session_id, user.team_id, user.id),
                        )
                        msgs: list[ChatMessage] = [
                            ChatMessage(role="system", content=(st.messages[0].content if st.messages else ""))
                        ]
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
                            session_id=req.session_id,
                            user_id=user.id,
                            team_id=user.team_id,
                            messages=msgs,
                            max_messages=max(0, int(settings.max_session_messages)),
                            max_chars=max(0, int(settings.max_context_chars)),
                        )
            except Exception:
                pass

        result = await service.chat(
            message=req.message,
            session_id=req.session_id,
            role=req.role,
            user_id=user.id,
            team_id=user.team_id,
            provider=req.provider,
            model=req.model,
            workspace_root=workspace_root,
            security_preset=req.security_preset,
            enable_shell=req.enable_shell,
            enable_write=req.enable_write,
            enable_browser=req.enable_browser,
            enable_dangerous=req.enable_dangerous,
            show_reasoning=req.show_reasoning,
            attachments=req.attachments,
            team_skills_prompt=team_prompt or None,
        )

        # Persist: session + messages + files (best-effort; should not affect chat response if it fails).
        try:
            now = utc_now_iso()
            sid = str(result.get("session_id") or "").strip()
            if sid:
                provider_name = (req.provider or settings.provider or "openai").strip().lower()
                model_name = (req.model or settings.model or "").strip()
                project_id = int(req.project_id) if req.project_id is not None and int(req.project_id) > 0 else None

                title = _truncate_title(req.message)
                await db.execute(
                    """
                    INSERT OR IGNORE INTO chat_sessions(
                      session_id, team_id, user_id, role, provider, model, project_id, title, opencode_session_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sid,
                        user.team_id,
                        user.id,
                        req.role,
                        provider_name,
                        model_name,
                        project_id,
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
                        project_id = ?,
                        opencode_session_id = COALESCE(opencode_session_id, ?),
                        title = CASE WHEN title = '' THEN ? ELSE title END
                    WHERE session_id = ? AND team_id = ? AND user_id = ?
                    """,
                    (
                        now,
                        req.role,
                        provider_name,
                        model_name,
                        project_id,
                        result.get("opencode_session_id"),
                        title,
                        sid,
                        user.team_id,
                        user.id,
                    ),
                )

                user_attachments = req.attachments or []
                await db.execute(
                    """
                    INSERT INTO chat_messages(session_id, team_id, user_id, role, content, attachments_json, events_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        sid,
                        user.team_id,
                        user.id,
                        "user",
                        req.message,
                        json.dumps(user_attachments, ensure_ascii=False),
                        now,
                    ),
                )
                await db.execute(
                    """
                    INSERT INTO chat_messages(session_id, team_id, user_id, role, content, attachments_json, events_json, created_at)
                    VALUES (?, ?, ?, ?, ?, '[]', ?, ?)
                    """,
                    (
                        sid,
                        user.team_id,
                        user.id,
                        "assistant",
                        str(result.get("assistant") or ""),
                        json.dumps(result.get("events") or [], ensure_ascii=False),
                        now,
                    ),
                )

                # Index files (uploads + generated outputs)
                files_to_index: list[dict] = []
                for a in user_attachments:
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
                            "kind": _infer_kind(a),
                        }
                    )

                files_to_index.extend(_extract_tool_files(list(result.get("events") or [])))

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
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            fid,
                            user.team_id,
                            user.id,
                            project_id,
                            sid,
                            kind,
                            filename,
                            ctype,
                            size_bytes,
                            now,
                        ),
                    )
                    # Back-fill association if the record already exists (e.g. uploaded before sending the message).
                    await db.execute(
                        """
                        UPDATE file_records
                        SET project_id = COALESCE(project_id, ?),
                            session_id = COALESCE(session_id, ?)
                        WHERE file_id = ? AND team_id = ? AND user_id = ?
                        """,
                        (project_id, sid, fid, user.team_id, user.id),
                    )

                await db.commit()

                try:
                    await sync_session_snapshot_from_db(
                        settings=settings,
                        db=db,
                        team_id=user.team_id,
                        user_id=user.id,
                        session_id=sid,
                    )
                except Exception:
                    pass
        except Exception:
            # Don't break chat on persistence issues (dev UX). Logs are available in server output.
            pass

        return ChatResponse(session_id=result["session_id"], assistant=result["assistant"], events=result["events"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
