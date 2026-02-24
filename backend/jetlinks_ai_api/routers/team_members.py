from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from ..db import fetchall, fetchone, row_to_dict, rows_to_dicts, utc_now_iso
from ..deps import CurrentUser, get_current_user, get_db, require_team_admin
from ..services.auth_service import hash_password


router = APIRouter(tags=["team"])

class TeamMember(BaseModel):
    user_id: int
    email: str
    name: str
    role: str
    joined_at: str


@router.get("/team/members", response_model=list[TeamMember])
async def list_team_members(
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> list[TeamMember]:
    rows = await fetchall(
        db,
        """
        SELECT u.id AS user_id, u.email AS email, u.name AS name, m.role AS role, m.created_at AS joined_at
        FROM memberships m
        JOIN users u ON u.id = m.user_id
        WHERE m.team_id = ?
        ORDER BY m.created_at ASC
        """,
        (user.team_id,),
    )
    return [TeamMember(**r) for r in rows_to_dicts(list(rows))]


class AddMemberRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=60)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    role: str = Field(default="member", pattern=r"^(owner|admin|member)$")


@router.post("/team/members", response_model=TeamMember)
async def add_team_member(
    req: AddMemberRequest,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> TeamMember:
    require_team_admin(user)

    email = str(req.email).strip().lower()
    existing_user_row = await fetchone(db, "SELECT id, email, name FROM users WHERE email = ?", (email,))
    existing_user = row_to_dict(existing_user_row)

    now = utc_now_iso()
    if existing_user:
        user_id = int(existing_user["id"])
    else:
        if not req.password:
            raise HTTPException(status_code=400, detail="新成员必须设置初始密码")
        pwd_hash = hash_password(req.password)
        cur = await db.execute(
            "INSERT INTO users(email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (email, req.name.strip(), pwd_hash, now),
        )
        user_id = int(cur.lastrowid)

    # owner 权限仅允许 owner 授予
    if req.role == "owner" and user.team_role != "owner":
        raise HTTPException(status_code=403, detail="只有 owner 可以授予 owner 角色")

    # already member?
    mem_row = await fetchone(
        db,
        "SELECT user_id FROM memberships WHERE user_id = ? AND team_id = ?",
        (user_id, user.team_id),
    )
    if row_to_dict(mem_row):
        raise HTTPException(status_code=400, detail="该用户已在团队中")

    await db.execute(
        "INSERT INTO memberships(user_id, team_id, role, created_at) VALUES (?, ?, ?, ?)",
        (user_id, user.team_id, req.role, now),
    )
    await db.commit()

    row = await fetchone(
        db,
        """
        SELECT u.id AS user_id, u.email AS email, u.name AS name, m.role AS role, m.created_at AS joined_at
        FROM memberships m
        JOIN users u ON u.id = m.user_id
        WHERE m.team_id = ? AND m.user_id = ?
        """,
        (user.team_id, user_id),
    )
    data = row_to_dict(row)
    if not data:
        raise HTTPException(status_code=500, detail="添加失败")
    return TeamMember(**data)


class UpdateMemberRoleRequest(BaseModel):
    role: str = Field(pattern=r"^(owner|admin|member)$")


@router.put("/team/members/{member_user_id}", response_model=TeamMember)
async def update_team_member_role(
    member_user_id: int,
    req: UpdateMemberRoleRequest,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> TeamMember:
    # 仅 owner 可以改角色（避免 admin 互相加权）
    if user.team_role != "owner":
        raise HTTPException(status_code=403, detail="只有 owner 可以修改成员角色")

    if int(member_user_id) == user.id and req.role != "owner":
        raise HTTPException(status_code=400, detail="不能把自己降级")

    await db.execute(
        "UPDATE memberships SET role = ? WHERE team_id = ? AND user_id = ?",
        (req.role, user.team_id, int(member_user_id)),
    )
    await db.commit()

    row = await fetchone(
        db,
        """
        SELECT u.id AS user_id, u.email AS email, u.name AS name, m.role AS role, m.created_at AS joined_at
        FROM memberships m
        JOIN users u ON u.id = m.user_id
        WHERE m.team_id = ? AND m.user_id = ?
        """,
        (user.team_id, int(member_user_id)),
    )
    data = row_to_dict(row)
    if not data:
        raise HTTPException(status_code=404, detail="成员不存在")
    return TeamMember(**data)


@router.delete("/team/members/{member_user_id}")
async def remove_team_member(
    member_user_id: int,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    require_team_admin(user)

    if int(member_user_id) == user.id:
        raise HTTPException(status_code=400, detail="不能把自己移出团队")

    mem_row = await fetchone(
        db,
        "SELECT role FROM memberships WHERE team_id = ? AND user_id = ?",
        (user.team_id, int(member_user_id)),
    )
    mem = row_to_dict(mem_row)
    if not mem:
        raise HTTPException(status_code=404, detail="成员不存在")
    if str(mem.get("role") or "") == "owner":
        raise HTTPException(status_code=403, detail="不能移除 owner")

    await db.execute("DELETE FROM memberships WHERE team_id = ? AND user_id = ?", (user.team_id, int(member_user_id)))
    await db.commit()
    return {"ok": True}
