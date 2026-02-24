from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, Response

from ..db import fetchone, row_to_dict
from ..deps import get_current_user, get_db, get_settings
from ..project_utils import resolve_project_path, resolve_user_workspace_root
from ..services.auth_service import validate_download_token
from ..services.prototype_service import PrototypeService
from ..services.workspace_output_service import save_output_to_workspace


router = APIRouter(tags=["prototype"])

_PROTOTYPE_ID_RE = re.compile(r"^prototype_[a-f0-9]{32}$", re.IGNORECASE)
_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)

_MIME_BY_EXT = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
}


async def _resolve_workspace_root(
    *,
    project_id: int | None,
    user,
    settings,
    db,
) -> Path:
    if project_id is not None and int(project_id) > 0:
        proj_row = await fetchone(
            db,
            "SELECT id, team_id, path, enabled FROM team_projects WHERE id = ?",
            (int(project_id),),
        )
        proj = row_to_dict(proj_row) or {}
        if not proj or int(proj.get("team_id") or 0) != int(getattr(user, "team_id", 0)):
            raise HTTPException(status_code=404, detail="项目不存在")
        if not bool(proj.get("enabled")):
            raise HTTPException(status_code=400, detail="项目已禁用")
        try:
            return resolve_project_path(settings, str(proj.get("path") or ""))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"项目路径无效：{e}") from e

    ws_row = await fetchone(db, "SELECT workspace_path FROM team_settings WHERE team_id = ?", (user.team_id,))
    ws = str((row_to_dict(ws_row) or {}).get("workspace_path") or "").strip()
    if ws:
        try:
            base = resolve_project_path(settings, ws)
        except ValueError:
            base = settings.workspace_root
    else:
        base = settings.workspace_root
    try:
        return resolve_user_workspace_root(
            settings,
            Path(base),
            user.team_id,
            user.id,
            user.team_name,
            user.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"用户工作区路径无效：{e}") from e


def _append_token_to_hrefs(html: str, token: str) -> str:
    def repl(m):  # noqa: ANN001
        href = str(m.group(1) or "")
        if not href:
            return m.group(0)
        lowered = href.lower()
        if lowered.startswith(("http://", "https://", "//", "mailto:", "tel:", "#")):
            return m.group(0)
        if "token=" in lowered:
            return m.group(0)
        sep = "&" if "?" in href else "?"
        return f'href="{href}{sep}token={token}"'

    return _HREF_RE.sub(repl, html)


def _safe_prototype_file(outputs_dir, prototype_id: str, file_path: str):  # noqa: ANN001
    if not _PROTOTYPE_ID_RE.match(prototype_id):
        raise HTTPException(status_code=400, detail="invalid prototype_id")

    value = (file_path or "").lstrip("/").lstrip("\\")
    if not value or ".." in value:
        raise HTTPException(status_code=400, detail="invalid path")

    base = (outputs_dir / prototype_id).resolve()
    full = (base / value).resolve()
    if full == base or not str(full).startswith(str(base) + os.sep):
        raise HTTPException(status_code=400, detail="invalid path")
    return full


class PrototypePage(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    slug: str | None = None


class PrototypeRequest(BaseModel):
    project_name: str = Field(min_length=1)
    pages: list[PrototypePage] = Field(min_length=1)


@router.post("/prototype/generate")
async def generate_prototype(
    req: PrototypeRequest,
    project_id: int | None = Query(default=None),
    user=Depends(get_current_user),  # noqa: ANN001
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    service = PrototypeService(settings)
    try:
        meta = await service.generate(
            project_name=req.project_name,
            pages=[p.model_dump() for p in req.pages],
        )
        try:
            workspace_root = await _resolve_workspace_root(
                project_id=project_id,
                user=user,
                settings=settings,
                db=db,
            )
            workspace_meta = save_output_to_workspace(
                settings=settings,
                workspace_root=workspace_root,
                file_id=str(meta.get("file_id") or ""),
                title=req.project_name,
                kind="prototype_zip",
                payload=req.model_dump(),
                meta=meta,
                source="/api/prototype/generate",
            )
            meta.update(workspace_meta)
        except Exception:
            pass
        return meta
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/prototype/preview/{prototype_id}/{file_path:path}")
async def preview_prototype_file(
    prototype_id: str,
    file_path: str,
    token: str = Query(min_length=1),
    settings=Depends(get_settings),  # noqa: ANN001
):
    try:
        validate_download_token(settings=settings, token=token, file_id=prototype_id)
    except Exception:
        raise HTTPException(status_code=401, detail="预览链接已失效，请重新生成") from None

    full = _safe_prototype_file(settings.outputs_dir, prototype_id, file_path)
    if not full.exists() or not full.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    ext = full.suffix.lower()
    media_type = _MIME_BY_EXT.get(ext, "application/octet-stream")
    headers = {"cache-control": "no-store"}

    if ext == ".html":
        text = full.read_text(encoding="utf-8", errors="replace")
        return Response(content=_append_token_to_hrefs(text, token), media_type=media_type, headers=headers)

    return FileResponse(path=full, media_type=media_type, filename=full.name, headers=headers)
