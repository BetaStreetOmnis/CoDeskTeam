from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import fetchall, fetchone, row_to_dict, rows_to_dicts, utc_now_iso
from ..deps import CurrentUser, get_current_user, get_db, get_settings
from ..services.team_skill_seed_service import ensure_default_team_skills


router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_super(user: CurrentUser, settings) -> None:  # noqa: ANN001
    if str(user.email or "").strip().lower() not in settings.super_emails:
        raise HTTPException(status_code=403, detail="需要超级管理员权限")


class AdminTeam(BaseModel):
    id: int
    name: str
    created_at: str
    members: int = 0


@router.get("/teams", response_model=list[AdminTeam])
async def list_admin_teams(
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> list[AdminTeam]:
    _require_super(user, settings)
    rows = await fetchall(
        db,
        """
        SELECT
          t.id AS id,
          t.name AS name,
          t.created_at AS created_at,
          (SELECT COUNT(1) FROM memberships m WHERE m.team_id = t.id) AS members
        FROM teams t
        ORDER BY t.id ASC
        """,
    )
    return [AdminTeam(**r) for r in rows_to_dicts(list(rows))]


class CreateAdminTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@router.post("/teams", response_model=AdminTeam)
async def create_admin_team(
    req: CreateAdminTeamRequest,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> AdminTeam:
    _require_super(user, settings)
    name = str(req.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="团队名称不能为空")

    now = utc_now_iso()
    cur = await db.execute("INSERT INTO teams(name, created_at) VALUES (?, ?)", (name, now))
    team_id = int(cur.lastrowid or 0)
    if not team_id:
        raise HTTPException(status_code=500, detail="创建团队失败")

    # Make the creator an owner so they can bootstrap (create invites, grant roles, etc.).
    await db.execute(
        "INSERT OR IGNORE INTO memberships(user_id, team_id, role, created_at) VALUES (?, ?, ?, ?)",
        (int(user.id), int(team_id), "owner", now),
    )
    await db.commit()

    # Best-effort: seed default team skills for a better out-of-box experience.
    try:
        await ensure_default_team_skills(db, team_id=int(team_id))
    except Exception:
        pass

    row = await fetchone(
        db,
        """
        SELECT
          t.id AS id,
          t.name AS name,
          t.created_at AS created_at,
          (SELECT COUNT(1) FROM memberships m WHERE m.team_id = t.id) AS members
        FROM teams t
        WHERE t.id = ?
        """,
        (int(team_id),),
    )
    data = row_to_dict(row)
    if not data:
        raise HTTPException(status_code=500, detail="创建团队失败")
    return AdminTeam(**data)


class UpdateAdminTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@router.put("/teams/{team_id}", response_model=AdminTeam)
async def update_admin_team(
    team_id: int,
    req: UpdateAdminTeamRequest,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> AdminTeam:
    _require_super(user, settings)
    name = str(req.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="团队名称不能为空")

    await db.execute("UPDATE teams SET name = ? WHERE id = ?", (name, int(team_id)))
    await db.commit()

    row = await fetchone(
        db,
        """
        SELECT
          t.id AS id,
          t.name AS name,
          t.created_at AS created_at,
          (SELECT COUNT(1) FROM memberships m WHERE m.team_id = t.id) AS members
        FROM teams t
        WHERE t.id = ?
        """,
        (int(team_id),),
    )
    data = row_to_dict(row)
    if not data:
        raise HTTPException(status_code=404, detail="团队不存在")
    return AdminTeam(**data)

