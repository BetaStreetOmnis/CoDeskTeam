from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..agent.types import ChatMessage
from ..db import fetchall, fetchone, row_to_dict, rows_to_dicts, utc_now_iso
from ..deps import get_db, get_settings
from ..project_utils import resolve_project_path, resolve_user_workspace_root
from ..services.agent_service import AgentService
from ..services.auth_service import hash_password
from ..services.history_file_store import sync_session_snapshot_from_db
from ..services.team_skill_seed_service import ensure_default_team_skills
from ..session_store import get_session_store


router = APIRouter(tags=["integrations"])

_FILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


def _extract_integration_token(request: Request) -> str | None:
    token = str(request.headers.get("x-jetlinks-ai-integration-token") or "").strip()
    if token:
        return token
    token = str(request.headers.get("x-aistaff-integration-token") or "").strip()
    if token:
        return token
    auth = str(request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth.split(None, 1)[1].strip()
    return None


def _external_email(*, team_id: int, provider: str, external_id: str) -> str:
    raw = f"{provider}:{team_id}:{external_id}".encode("utf-8", errors="ignore")
    digest = hashlib.sha256(raw).digest()
    short = base64.b32encode(digest).decode("ascii").rstrip("=").lower()[:16]
    return f"ext+{provider}+t{int(team_id)}+{short}@aistaff.local"


def _openclaw_session_id(*, team_id: int, thread_id: str, external_user_id: str) -> str:
    base = (thread_id or "").strip() or (external_user_id or "").strip()
    raw = f"openclaw:{int(team_id)}:{base}".encode("utf-8", errors="ignore")
    digest = hashlib.sha1(raw).hexdigest()  # noqa: S324 - non-crypto use (stable id)
    return f"oc-{int(team_id)}-{digest[:24]}"


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
        result = ev.get("result") if isinstance(ev.get("result"), dict) else {}
        fid = str(result.get("file_id") or "").strip()
        if not fid:
            continue
        filename = str(result.get("filename") or fid).strip() or fid
        ctype = str(result.get("content_type") or "").strip().lower()
        kind = "file"
        if ctype.startswith("image/") or filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            kind = "image"
        out.append({"file_id": fid, "filename": filename, "content_type": ctype, "kind": kind})
    return out


async def _get_or_create_openclaw_user(
    *,
    db: object,
    team_id: int,
    team_name: str,
    external_user_id: str,
    display_name: str | None,
) -> dict[str, object]:
    provider = "openclaw"
    ext = (external_user_id or "").strip()
    if not ext:
        raise ValueError("external_user_id is empty")

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


async def _build_team_skills_prompt(db: object, *, team_id: int) -> str:
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


class OpenclawMessageRequest(BaseModel):
    external_user_id: str = Field(min_length=1, max_length=300)
    external_display_name: str | None = Field(default=None, max_length=200)
    thread_id: str | None = Field(default=None, max_length=200)
    message: str = Field(min_length=1, max_length=40_000)

    provider: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=80)
    role: str = Field(default="general", max_length=40)

    security_preset: str | None = Field(default="safe", max_length=40)
    enable_shell: bool | None = None
    enable_write: bool | None = None
    enable_browser: bool | None = None
    enable_dangerous: bool | None = None
    show_reasoning: bool | None = None

    attachments: list[dict] | None = None


class OpenclawMessageResponse(BaseModel):
    session_id: str
    assistant: str
    events: list[dict]


@router.post("/integrations/openclaw/message", response_model=OpenclawMessageResponse)
async def openclaw_message(
    req: OpenclawMessageRequest,
    request: Request,
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> OpenclawMessageResponse:
    token = _extract_integration_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="missing integration token")

    integ_row = await fetchone(
        db,
        """
        SELECT id, team_id, kind, revoked_at
        FROM integration_tokens
        WHERE token = ?
        """,
        (token,),
    )
    integ = row_to_dict(integ_row) or {}
    if not integ:
        raise HTTPException(status_code=401, detail="invalid integration token")
    if str(integ.get("kind") or "") != "openclaw":
        raise HTTPException(status_code=401, detail="invalid integration token kind")
    if str(integ.get("revoked_at") or "").strip():
        raise HTTPException(status_code=401, detail="integration token revoked")

    team_id = int(integ.get("team_id") or 0)
    if team_id <= 0:
        raise HTTPException(status_code=401, detail="invalid integration token team")

    team_row = await fetchone(db, "SELECT id, name FROM teams WHERE id = ?", (team_id,))
    team = row_to_dict(team_row) or {}
    if not team:
        raise HTTPException(status_code=400, detail="team not found")
    team_name = str(team.get("name") or f"team-{team_id}")

    try:
        user_info = await _get_or_create_openclaw_user(
            db=db,
            team_id=team_id,
            team_name=team_name,
            external_user_id=req.external_user_id,
            display_name=req.external_display_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    user_id = int(user_info["id"])
    user_name = str(user_info.get("name") or "").strip() or req.external_user_id

    # Resolve workspace root (team settings + per-user layout)
    base_workspace = settings.workspace_root
    ws_row = await fetchone(db, "SELECT workspace_path FROM team_settings WHERE team_id = ?", (team_id,))
    ws = str((row_to_dict(ws_row) or {}).get("workspace_path") or "").strip()
    if ws:
        try:
            base_workspace = resolve_project_path(settings, ws)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"团队工作区路径无效：{e}") from e

    try:
        workspace_root = resolve_user_workspace_root(
            settings,
            Path(base_workspace),
            team_id,
            user_id,
            team_name,
            user_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"用户工作区路径无效：{e}") from e

    # Best-effort: seed defaults for the team (doesn't affect prompts unless enabled).
    try:
        await ensure_default_team_skills(db, team_id=team_id)
    except Exception:
        pass
    team_prompt = await _build_team_skills_prompt(db, team_id=team_id)

    session_id = _openclaw_session_id(
        team_id=team_id,
        thread_id=str(req.thread_id or "").strip() or req.external_user_id,
        external_user_id=req.external_user_id,
    )

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
                    role=req.role,
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

    service = AgentService(settings)
    try:
        result = await service.chat(
            message=req.message,
            session_id=session_id,
            role=req.role,
            user_id=user_id,
            team_id=team_id,
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    # Persist session + messages (best-effort).
    try:
        now = utc_now_iso()
        provider_name = (req.provider or settings.provider or "openai").strip().lower()
        model_name = (req.model or settings.model or "").strip()
        title = f"[openclaw] {user_name}".strip()

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
                req.role,
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
                req.role,
                provider_name,
                model_name,
                result.get("opencode_session_id"),
                title,
                session_id,
                team_id,
                user_id,
            ),
        )

        user_attachments = req.attachments or []
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
                session_id,
                team_id,
                user_id,
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
            await sync_session_snapshot_from_db(
                settings=settings,
                db=db,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            )
        except Exception:
            pass
    except Exception:
        pass

    sid = str(result.get("session_id") or "").strip() or session_id
    assistant = str(result.get("assistant") or "")
    events = list(result.get("events") or [])
    return OpenclawMessageResponse(session_id=sid, assistant=assistant, events=events)
