from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..db import fetchall, rows_to_dicts
from ..deps import CurrentUser, get_current_user, get_db, get_settings


router = APIRouter(tags=["team"])


class TeamOverview(BaseModel):
    id: int
    name: str
    role: str
    created_at: str
    members: int = 0
    projects: int = 0
    skills: int = 0
    requirements_total: int = 0
    requirements_incoming: int = 0
    requirements_todo: int = 0
    requirements_in_progress: int = 0
    requirements_done: int = 0
    requirements_blocked: int = 0
    workspace_path: str | None = None
    last_activity_at: str | None = None


@router.get("/team/teams", response_model=list[TeamOverview])
async def list_my_teams(
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
    settings=Depends(get_settings),  # noqa: ANN001
) -> list[TeamOverview]:
    is_super = str(user.email).strip().lower() in set(getattr(settings, "super_emails", set()) or set())
    if is_super:
        rows = await fetchall(
            db,
            """
            SELECT
              t.id AS id,
              t.name AS name,
              COALESCE(NULLIF(TRIM(m.role), ''), 'admin') AS role,
              t.created_at AS created_at,
              COALESCE((SELECT COUNT(1) FROM memberships mm WHERE mm.team_id = t.id), 0) AS members,
              COALESCE((SELECT COUNT(1) FROM team_projects p WHERE p.team_id = t.id AND p.enabled = 1), 0) AS projects,
              COALESCE((SELECT COUNT(1) FROM team_skills s WHERE s.team_id = t.id), 0) AS skills,
              COALESCE((SELECT COUNT(1) FROM team_requirements r WHERE r.team_id = t.id), 0) AS requirements_total,
              COALESCE((SELECT COUNT(1) FROM team_requirements r WHERE r.team_id = t.id AND r.status = 'incoming'), 0) AS requirements_incoming,
              COALESCE((SELECT COUNT(1) FROM team_requirements r WHERE r.team_id = t.id AND r.status = 'todo'), 0) AS requirements_todo,
              COALESCE((SELECT COUNT(1) FROM team_requirements r WHERE r.team_id = t.id AND r.status = 'in_progress'), 0) AS requirements_in_progress,
              COALESCE((SELECT COUNT(1) FROM team_requirements r WHERE r.team_id = t.id AND r.status = 'done'), 0) AS requirements_done,
              COALESCE((SELECT COUNT(1) FROM team_requirements r WHERE r.team_id = t.id AND r.status = 'blocked'), 0) AS requirements_blocked,
              (SELECT workspace_path FROM team_settings ts WHERE ts.team_id = t.id LIMIT 1) AS workspace_path,
              (
                SELECT MAX(x) FROM (
                  SELECT MAX(updated_at) AS x FROM team_projects p2 WHERE p2.team_id = t.id
                  UNION ALL
                  SELECT MAX(updated_at) AS x FROM team_requirements r2 WHERE r2.team_id = t.id
                  UNION ALL
                  SELECT MAX(updated_at) AS x FROM team_skills s2 WHERE s2.team_id = t.id
                  UNION ALL
                  SELECT MAX(updated_at) AS x FROM team_settings ts2 WHERE ts2.team_id = t.id
                ) v
              ) AS last_activity_at
            FROM teams t
            LEFT JOIN memberships m ON m.team_id = t.id AND m.user_id = ?
            ORDER BY t.id ASC
            """,
            (int(user.id),),
        )
    else:
        rows = await fetchall(
            db,
            """
            SELECT
              t.id AS id,
              t.name AS name,
              m.role AS role,
              t.created_at AS created_at,
              COALESCE((SELECT COUNT(1) FROM memberships mm WHERE mm.team_id = t.id), 0) AS members,
              COALESCE((SELECT COUNT(1) FROM team_projects p WHERE p.team_id = t.id AND p.enabled = 1), 0) AS projects,
              COALESCE((SELECT COUNT(1) FROM team_skills s WHERE s.team_id = t.id), 0) AS skills,
              COALESCE((SELECT COUNT(1) FROM team_requirements r WHERE r.team_id = t.id), 0) AS requirements_total,
              COALESCE((SELECT COUNT(1) FROM team_requirements r WHERE r.team_id = t.id AND r.status = 'incoming'), 0) AS requirements_incoming,
              COALESCE((SELECT COUNT(1) FROM team_requirements r WHERE r.team_id = t.id AND r.status = 'todo'), 0) AS requirements_todo,
              COALESCE((SELECT COUNT(1) FROM team_requirements r WHERE r.team_id = t.id AND r.status = 'in_progress'), 0) AS requirements_in_progress,
              COALESCE((SELECT COUNT(1) FROM team_requirements r WHERE r.team_id = t.id AND r.status = 'done'), 0) AS requirements_done,
              COALESCE((SELECT COUNT(1) FROM team_requirements r WHERE r.team_id = t.id AND r.status = 'blocked'), 0) AS requirements_blocked,
              (SELECT workspace_path FROM team_settings ts WHERE ts.team_id = t.id LIMIT 1) AS workspace_path,
              (
                SELECT MAX(x) FROM (
                  SELECT MAX(updated_at) AS x FROM team_projects p2 WHERE p2.team_id = t.id
                  UNION ALL
                  SELECT MAX(updated_at) AS x FROM team_requirements r2 WHERE r2.team_id = t.id
                  UNION ALL
                  SELECT MAX(updated_at) AS x FROM team_skills s2 WHERE s2.team_id = t.id
                  UNION ALL
                  SELECT MAX(updated_at) AS x FROM team_settings ts2 WHERE ts2.team_id = t.id
                ) v
              ) AS last_activity_at
            FROM memberships m
            JOIN teams t ON t.id = m.team_id
            WHERE m.user_id = ?
            ORDER BY t.id ASC
            """,
            (int(user.id),),
        )
    return [TeamOverview(**r) for r in rows_to_dicts(list(rows))]
