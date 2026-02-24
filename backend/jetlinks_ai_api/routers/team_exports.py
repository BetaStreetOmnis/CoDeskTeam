from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..db import fetchone, row_to_dict
from ..deps import CurrentUser, get_current_user, get_db, get_settings
from ..project_utils import resolve_project_path, resolve_user_workspace_root
from ..services.team_export_service import export_team_db_to_markdown


router = APIRouter(tags=["team"])


class TeamDbExportResponse(BaseModel):
    ok: bool
    updated_at: str
    workspace_root: str
    workspace_path: str
    bytes: int
    filename: str


async def _resolve_workspace_root(
    *,
    project_id: int | None,
    user: CurrentUser,
    settings,
    db,
) -> Path:  # noqa: ANN001
    # Match docs/chat behavior:
    # - If a project is selected, export into that project directory.
    # - Otherwise export into the team's workspace, applying per-user layout if enabled.
    if project_id is not None and int(project_id) > 0:
        proj_row = await fetchone(
            db,
            "SELECT id, team_id, path, enabled FROM team_projects WHERE id = ?",
            (int(project_id),),
        )
        proj = row_to_dict(proj_row) or {}
        if not proj or int(proj.get("team_id") or 0) != int(user.team_id):
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


@router.post("/team/export-md", response_model=TeamDbExportResponse)
async def export_team_db_md(
    project_id: int | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> TeamDbExportResponse:
    workspace_root = await _resolve_workspace_root(project_id=project_id, user=user, settings=settings, db=db)
    try:
        result = await export_team_db_to_markdown(
            db=db,
            team_id=int(user.team_id),
            team_name=getattr(user, "team_name", None),
            user_email=getattr(user, "email", None),
            user_name=getattr(user, "name", None),
            workspace_root=workspace_root,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return TeamDbExportResponse(**result)

