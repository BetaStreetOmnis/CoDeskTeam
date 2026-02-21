from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from ..db import fetchall, fetchone, row_to_dict, rows_to_dicts
from ..time_utils import UTC
from ..deps import CurrentUser, get_current_user, get_db, require_team_admin


router = APIRouter(tags=["team"])

def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


class TeamInvite(BaseModel):
    id: int
    team_id: int
    email: str | None
    role: str
    token: str
    created_by: int | None
    created_at: str
    expires_at: str
    used_at: str | None
    used_by: int | None


class CreateInviteRequest(BaseModel):
    email: EmailStr | None = None
    role: str = Field(default="member", pattern=r"^(admin|member)$")
    expires_days: int = Field(default=7, ge=1, le=365)


@router.get("/team/invites", response_model=list[TeamInvite])
async def list_team_invites(
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> list[TeamInvite]:
    require_team_admin(user)
    rows = await fetchall(
        db,
        """
        SELECT id, team_id, email, role, token, created_by, created_at, expires_at, used_at, used_by
        FROM invites
        WHERE team_id = ?
        ORDER BY id DESC
        LIMIT 100
        """,
        (user.team_id,),
    )
    return [TeamInvite(**r) for r in rows_to_dicts(list(rows))]


@router.post("/team/invites", response_model=TeamInvite)
async def create_team_invite(
    req: CreateInviteRequest,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> TeamInvite:
    require_team_admin(user)
    if req.role == "admin" and user.team_role != "owner":
        raise HTTPException(status_code=403, detail="只有 owner 可以创建 admin 邀请")

    now = datetime.now(tz=UTC)
    created_at = _iso(now)
    expires_at = _iso(now + timedelta(days=int(req.expires_days)))
    email = str(req.email).strip().lower() if req.email is not None else None

    token: str | None = None
    for _ in range(5):
        candidate = secrets.token_urlsafe(18)
        existing = await fetchone(db, "SELECT id FROM invites WHERE token = ?", (candidate,))
        if not row_to_dict(existing):
            token = candidate
            break
    if not token:
        raise HTTPException(status_code=500, detail="生成邀请码失败")

    cur = await db.execute(
        """
        INSERT INTO invites(team_id, email, role, token, created_by, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user.team_id, email, req.role, token, user.id, created_at, expires_at),
    )
    invite_id = int(cur.lastrowid)
    await db.commit()

    row = await fetchone(
        db,
        """
        SELECT id, team_id, email, role, token, created_by, created_at, expires_at, used_at, used_by
        FROM invites
        WHERE id = ?
        """,
        (invite_id,),
    )
    data = row_to_dict(row)
    if not data:
        raise HTTPException(status_code=500, detail="创建邀请码失败")
    return TeamInvite(**data)


@router.delete("/team/invites/{invite_id}")
async def delete_team_invite(
    invite_id: int,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    require_team_admin(user)
    row = await fetchone(db, "SELECT id, team_id FROM invites WHERE id = ?", (int(invite_id),))
    data = row_to_dict(row)
    if not data or int(data["team_id"]) != user.team_id:
        raise HTTPException(status_code=404, detail="邀请码不存在")
    await db.execute("DELETE FROM invites WHERE id = ?", (int(invite_id),))
    await db.commit()
    return {"ok": True}
