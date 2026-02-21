from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import fetchall, fetchone, row_to_dict, rows_to_dicts
from ..deps import CurrentUser, get_current_user, get_db, get_settings
from ..project_utils import resolve_project_path, resolve_user_workspace_root
from ..services.auth_service import create_download_token
from ..services.history_file_store import delete_session_snapshot, history_user_dir, sync_recent_session_snapshots_from_db
from ..url_utils import abs_url


router = APIRouter(tags=["history"])



_RG_LINE_RE = re.compile(r"^(.*?):(\d+):(\d+):(.*)$")


class HistorySearchHit(BaseModel):
    source: Literal["workspace", "history"]
    rel_path: str
    absolute_path: str
    line_no: int
    column_no: int
    preview: str


def _iter_text_files_fallback(base_path: Path):  # noqa: ANN201
    try:
        for path in base_path.rglob("*"):
            if not path.is_file():
                continue
            if any(part.startswith(".") for part in path.parts):
                continue
            yield path
    except Exception:
        return


def _directory_search(
    *,
    base_path: Path,
    query: str,
    source: Literal["workspace", "history"],
    limit: int,
) -> list[HistorySearchHit]:
    if limit <= 0:
        return []

    base = base_path.resolve()
    if not base.exists() or not base.is_dir():
        return []

    hits: list[HistorySearchHit] = []
    rg_bin = shutil.which("rg")

    if rg_bin:
        cmd = [
            rg_bin,
            "--line-number",
            "--column",
            "--no-heading",
            "--color",
            "never",
            "--smart-case",
            "--max-columns",
            "300",
            "--max-columns-preview",
            query,
            ".",
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(base),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=8,
                check=False,
            )
        except Exception:
            proc = None

        if proc and proc.returncode in {0, 1}:
            for line in (proc.stdout or "").splitlines():
                m = _RG_LINE_RE.match(line)
                if not m:
                    continue
                rel_path = m.group(1).lstrip("./")
                if not rel_path:
                    continue
                try:
                    line_no = int(m.group(2))
                    col_no = int(m.group(3))
                except Exception:
                    continue
                preview = m.group(4).strip()
                abs_path = (base / rel_path).resolve()
                hits.append(
                    HistorySearchHit(
                        source=source,
                        rel_path=rel_path,
                        absolute_path=str(abs_path),
                        line_no=line_no,
                        column_no=col_no,
                        preview=preview,
                    )
                )
                if len(hits) >= limit:
                    break
            return hits

    q = query.lower()
    for file_path in _iter_text_files_fallback(base):
        try:
            rel = file_path.relative_to(base).as_posix()
            with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
                for idx, raw in enumerate(handle, start=1):
                    pos = raw.lower().find(q)
                    if pos < 0:
                        continue
                    hits.append(
                        HistorySearchHit(
                            source=source,
                            rel_path=rel,
                            absolute_path=str(file_path.resolve()),
                            line_no=idx,
                            column_no=pos + 1,
                            preview=raw.strip(),
                        )
                    )
                    break
        except Exception:
            continue
        if len(hits) >= limit:
            break

    return hits


def _append_unique_target(targets: list[tuple[Literal["workspace", "history"], Path]], source: Literal["workspace", "history"], path: Path) -> None:
    try:
        resolved = path.expanduser().resolve()
    except Exception:
        return
    if not resolved.exists() or not resolved.is_dir():
        return
    if any(source == s and str(resolved) == str(p) for s, p in targets):
        return
    targets.append((source, resolved))


def _safe_join_dir(base_dir: Path, sub_path: str | None) -> Path:
    base = base_dir.expanduser().resolve()
    clean_sub_path = str(sub_path or "").strip().replace("\\", "/").strip("/")
    if not clean_sub_path:
        return base

    try:
        candidate = (base / clean_sub_path).resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="目录路径非法") from None

    try:
        _ = candidate.relative_to(base)
    except Exception:
        raise HTTPException(status_code=400, detail="目录路径非法") from None

    return candidate


def _search_target_path(base_dir: Path, sub_path: str | None) -> Path | None:
    try:
        target = _safe_join_dir(base_dir, sub_path)
    except HTTPException:
        raise
    except Exception:
        return None

    if not target.exists() or not target.is_dir():
        return None
    return target


def _has_history_snapshot_files(base_dir: Path) -> bool:
    try:
        if not base_dir.exists() or not base_dir.is_dir():
            return False
        for path in base_dir.rglob("*.json"):
            if path.is_file():
                return True
    except Exception:
        return False
    return False


def _safe_load_list(value: object) -> list[dict]:
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


class HistorySessionItem(BaseModel):
    session_id: str
    title: str = ""
    role: str
    provider: str
    model: str
    project_id: int | None = None
    created_at: str
    updated_at: str
    last_message: str | None = None


class HistoryAttachment(BaseModel):
    kind: str = Field(pattern="^(image|file)$")
    file_id: str
    filename: str | None = None
    content_type: str | None = None
    download_url: str


class HistoryMessageItem(BaseModel):
    id: int
    role: str = Field(pattern="^(user|assistant)$")
    content: str
    created_at: str
    attachments: list[HistoryAttachment] = Field(default_factory=list)
    events: object | None = None


class HistorySessionDetailResponse(BaseModel):
    session: HistorySessionItem
    messages: list[HistoryMessageItem]


@router.get("/history/sessions", response_model=list[HistorySessionItem])
async def list_sessions(
    project_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10_000),
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
):
    filters: list[str] = ["s.team_id = ?", "s.user_id = ?"]
    params: list[object] = [user.team_id, user.id]

    if project_id is not None:
        if int(project_id) <= 0:
            filters.append("s.project_id IS NULL")
        else:
            filters.append("s.project_id = ?")
            params.append(int(project_id))

    where = " AND ".join(filters)
    rows = await fetchall(
        db,
        f"""
        SELECT
          s.session_id,
          s.title,
          s.role,
          s.provider,
          s.model,
          s.project_id,
          s.created_at,
          s.updated_at,
          (
            SELECT m.content
            FROM chat_messages m
            WHERE m.session_id = s.session_id
            ORDER BY m.id DESC
            LIMIT 1
          ) AS last_message
        FROM chat_sessions s
        WHERE {where}
        ORDER BY s.updated_at DESC
        LIMIT ? OFFSET ?
        """,
        (*params, int(limit), int(offset)),
    )
    return [HistorySessionItem(**row_to_dict(r)) for r in rows]


@router.get("/history/sessions/{session_id}", response_model=HistorySessionDetailResponse)
async def get_session(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> HistorySessionDetailResponse:
    sess_row = await fetchone(
        db,
        """
        SELECT session_id, title, role, provider, model, project_id, created_at, updated_at,
          (
            SELECT m.content
            FROM chat_messages m
            WHERE m.session_id = s.session_id
            ORDER BY m.id DESC
            LIMIT 1
          ) AS last_message
        FROM chat_sessions s
        WHERE session_id = ? AND team_id = ? AND user_id = ?
        """,
        (session_id, user.team_id, user.id),
    )
    sess = row_to_dict(sess_row)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")

    msg_rows = await fetchall(
        db,
        """
        SELECT id, role, content, attachments_json, events_json, created_at
        FROM chat_messages
        WHERE session_id = ? AND team_id = ? AND user_id = ?
        ORDER BY id ASC
        """,
        (session_id, user.team_id, user.id),
    )

    messages: list[HistoryMessageItem] = []
    for r in msg_rows:
        m = row_to_dict(r) or {}
        atts_in = _safe_load_list(m.get("attachments_json"))
        atts_out: list[HistoryAttachment] = []
        for a in atts_in:
            fid = str(a.get("file_id") or "").strip()
            if not fid:
                continue
            kind = _infer_kind(a)
            token = create_download_token(settings=settings, file_id=fid)
            download_url = abs_url(settings, f"/api/files/{fid}?token={token}")
            atts_out.append(
                HistoryAttachment(
                    kind=kind,
                    file_id=fid,
                    filename=str(a.get("filename") or "") or None,
                    content_type=str(a.get("content_type") or "") or None,
                    download_url=download_url,
                )
            )

        events = None
        if m.get("events_json"):
            try:
                events = json.loads(str(m["events_json"]))
            except Exception:
                events = None

        messages.append(
            HistoryMessageItem(
                id=int(m.get("id") or 0),
                role=str(m.get("role") or ""),
                content=str(m.get("content") or ""),
                created_at=str(m.get("created_at") or ""),
                attachments=atts_out,
                events=events,
            )
        )

    return HistorySessionDetailResponse(session=HistorySessionItem(**sess), messages=messages)


@router.get("/history/search", response_model=list[HistorySearchHit])
async def search_history(
    q: str = Query(min_length=1, max_length=200),
    project_id: int | None = Query(default=None),
    sub_path: str | None = Query(default=None, max_length=600),
    include_workspace: bool = Query(default=True),
    include_history: bool = Query(default=True),
    limit: int = Query(default=80, ge=1, le=400),
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> list[HistorySearchHit]:
    query = str(q or "").strip()
    if not query:
        return []

    scope_sub_path = str(sub_path or "").strip().replace("\\", "/").strip("/") or None
    targets: list[tuple[Literal["workspace", "history"], Path]] = []

    def append_workspace_target(raw_path: str) -> None:
        p = str(raw_path or "").strip()
        if not p:
            return
        target = _search_target_path(Path(p), scope_sub_path)
        if target is None:
            return
        _append_unique_target(targets, "workspace", target)

    async def resolve_workspace_root_for_user() -> Path | None:
        ws_row = await fetchone(db, "SELECT workspace_path FROM team_settings WHERE team_id = ?", (user.team_id,))
        team_ws = str((row_to_dict(ws_row) or {}).get("workspace_path") or "").strip()
        if team_ws:
            try:
                base = resolve_project_path(settings, team_ws)
            except ValueError:
                base = settings.workspace_root
        else:
            base = settings.workspace_root

        try:
            return resolve_user_workspace_root(
                settings,
                base,
                user.team_id,
                user.id,
                user.team_name,
                user.name,
            )
        except Exception:
            return None

    if include_workspace:
        if project_id is None:
            rows = await fetchall(
                db,
                "SELECT path FROM team_projects WHERE team_id = ? AND enabled = 1 ORDER BY id DESC LIMIT 50",
                (user.team_id,),
            )
            for row in rows_to_dicts(list(rows)):
                append_workspace_target(str(row.get("path") or ""))

            resolved_root = await resolve_workspace_root_for_user()
            if resolved_root is not None:
                append_workspace_target(str(resolved_root))
        elif int(project_id) <= 0:
            resolved_root = await resolve_workspace_root_for_user()
            if resolved_root is not None:
                append_workspace_target(str(resolved_root))
        else:
            proj_row = await fetchone(
                db,
                "SELECT path, team_id FROM team_projects WHERE id = ?",
                (int(project_id),),
            )
            proj = row_to_dict(proj_row) or {}
            if not proj or int(proj.get("team_id") or 0) != user.team_id:
                raise HTTPException(status_code=404, detail="项目不存在")
            append_workspace_target(str(proj.get("path") or ""))

    if include_history:
        history_root = history_user_dir(settings, user.team_id, user.id)
        if not _has_history_snapshot_files(history_root):
            try:
                await sync_recent_session_snapshots_from_db(
                    settings=settings,
                    db=db,
                    team_id=user.team_id,
                    user_id=user.id,
                    limit=min(max(int(limit), 80), 300),
                )
            except Exception:
                pass

        history_target = _search_target_path(history_root, scope_sub_path)
        if history_target is not None:
            _append_unique_target(targets, "history", history_target)

    if not targets:
        return []

    out: list[HistorySearchHit] = []
    seen: set[tuple[str, int, int, str]] = set()

    for source, base in targets:
        remaining = int(limit) - len(out)
        if remaining <= 0:
            break
        hits = _directory_search(base_path=base, query=query, source=source, limit=min(remaining, 200))
        for hit in hits:
            key = (hit.absolute_path, hit.line_no, hit.column_no, hit.preview)
            if key in seen:
                continue
            seen.add(key)
            out.append(hit)
            if len(out) >= int(limit):
                break

    return out


@router.delete("/history/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    cur = await db.execute(
        "DELETE FROM chat_sessions WHERE session_id = ? AND team_id = ? AND user_id = ?",
        (session_id, user.team_id, user.id),
    )
    await db.commit()
    if cur.rowcount != 1:
        raise HTTPException(status_code=404, detail="session not found")
    delete_session_snapshot(settings=settings, team_id=user.team_id, user_id=user.id, session_id=session_id)
    return {"ok": True}


class HistoryFileItem(BaseModel):
    file_id: str
    kind: str
    filename: str
    content_type: str
    size_bytes: int
    project_id: int | None = None
    session_id: str | None = None
    created_at: str
    download_url: str


@router.get("/history/files", response_model=list[HistoryFileItem])
async def list_files(
    project_id: int | None = Query(default=None),
    session_id: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10_000),
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
):
    filters: list[str] = ["team_id = ?", "user_id = ?"]
    params: list[object] = [user.team_id, user.id]

    if project_id is not None:
        if int(project_id) <= 0:
            filters.append("project_id IS NULL")
        else:
            filters.append("project_id = ?")
            params.append(int(project_id))

    if session_id:
        filters.append("session_id = ?")
        params.append(str(session_id))

    if kind:
        k = str(kind).strip().lower()
        if k:
            filters.append("kind = ?")
            params.append(k)

    where = " AND ".join(filters)
    rows = await fetchall(
        db,
        f"""
        SELECT file_id, kind, filename, content_type, size_bytes, project_id, session_id, created_at
        FROM file_records
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (*params, int(limit), int(offset)),
    )
    out: list[HistoryFileItem] = []
    for r in rows:
        d = row_to_dict(r) or {}
        fid = str(d.get("file_id") or "")
        token = create_download_token(settings=settings, file_id=fid)
        download_url = abs_url(settings, f"/api/files/{fid}?token={token}")
        out.append(HistoryFileItem(**{**d, "download_url": download_url}))
    return out
