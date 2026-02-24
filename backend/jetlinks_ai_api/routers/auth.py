from __future__ import annotations

from datetime import datetime
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from ..db import fetchall, fetchone, row_to_dict, rows_to_dicts, utc_now_iso
from ..deps import CurrentUser, get_current_user, get_db, get_settings
from ..env_utils import env_str
from ..services.auth_service import create_access_token, hash_password, verify_password
from ..services.team_skill_seed_service import ensure_default_team_skills
from ..time_utils import UTC


router = APIRouter(tags=["auth"])


class AuthStatusResponse(BaseModel):
    setup_required: bool


@router.get("/auth/status", response_model=AuthStatusResponse)
async def auth_status(db=Depends(get_db)) -> AuthStatusResponse:  # noqa: ANN001
    row = await fetchone(db, "SELECT COUNT(1) AS c FROM users")
    c = int((row_to_dict(row) or {}).get("c") or 0)
    return AuthStatusResponse(setup_required=(c == 0))


class PublicTeam(BaseModel):
    id: int
    name: str


@router.get("/auth/teams", response_model=list[PublicTeam])
async def list_auth_teams(db=Depends(get_db)) -> list[PublicTeam]:  # noqa: ANN001
    rows = await fetchall(db, "SELECT id, name FROM teams ORDER BY id ASC")
    return [PublicTeam(**r) for r in rows_to_dicts(list(rows))]


class SetupRequest(BaseModel):
    team_name: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=60)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    team_id: int | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
    teams: list[dict]
    active_team: dict


@router.post("/auth/setup", response_model=AuthResponse)
async def setup(req: SetupRequest, settings=Depends(get_settings), db=Depends(get_db)) -> AuthResponse:  # noqa: ANN001
    row = await fetchone(db, "SELECT COUNT(1) AS c FROM users")
    c = int((row_to_dict(row) or {}).get("c") or 0)
    if c != 0:
        raise HTTPException(status_code=400, detail="系统已初始化，无需重复 setup")

    now = utc_now_iso()

    cur = await db.execute("INSERT INTO teams(name, created_at) VALUES (?, ?)", (req.team_name.strip(), now))
    team_id = int(cur.lastrowid)

    email = str(req.email).strip().lower()
    pwd_hash = hash_password(req.password)
    cur = await db.execute(
        "INSERT INTO users(email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (email, req.name.strip(), pwd_hash, now),
    )
    user_id = int(cur.lastrowid)

    await db.execute(
        "INSERT INTO memberships(user_id, team_id, role, created_at) VALUES (?, ?, ?, ?)",
        (user_id, team_id, "owner", now),
    )
    await db.commit()

    # Best-effort: seed default team skills for a better out-of-box experience.
    try:
        await ensure_default_team_skills(db, team_id=team_id)
    except Exception:
        pass

    token = create_access_token(settings=settings, user_id=user_id, email=email, team_id=team_id, team_role="owner")

    user = {"id": user_id, "email": email, "name": req.name.strip()}
    teams = [{"id": team_id, "name": req.team_name.strip(), "role": "owner"}]
    active_team = teams[0]
    return AuthResponse(access_token=token, user=user, teams=teams, active_team=active_team)


@router.post("/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest, settings=Depends(get_settings), db=Depends(get_db)) -> AuthResponse:  # noqa: ANN001
    email = str(req.email).strip().lower()
    user_row = await fetchone(
        db,
        "SELECT id, email, name, password_hash FROM users WHERE email = ?",
        (email,),
    )
    user = row_to_dict(user_row)
    if not user:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    if not verify_password(req.password, str(user["password_hash"])):
        raise HTTPException(status_code=401, detail="账号或密码错误")

    user_id = int(user["id"])
    is_super = email in settings.super_emails

    active_team: dict | None = None
    if req.team_id is not None:
        mem_row = await fetchone(
            db,
            """
            SELECT t.id AS id, t.name AS name, m.role AS role
            FROM memberships m
            JOIN teams t ON t.id = m.team_id
            WHERE m.user_id = ? AND m.team_id = ?
            """,
            (user_id, int(req.team_id)),
        )
        active_team = row_to_dict(mem_row)
        if not active_team and is_super:
            team_row = await fetchone(db, "SELECT id, name FROM teams WHERE id = ?", (int(req.team_id),))
            team = row_to_dict(team_row)
            if team:
                active_team = {"id": team["id"], "name": team["name"], "role": "admin"}
        if not active_team:
            raise HTTPException(status_code=403, detail="你不属于该团队")
    else:
        if is_super:
            team_row = await fetchone(db, "SELECT id, name FROM teams ORDER BY id ASC LIMIT 1")
            team = row_to_dict(team_row)
            if not team:
                raise HTTPException(status_code=403, detail="当前没有可用团队")
            mem_row = await fetchone(
                db,
                "SELECT role FROM memberships WHERE user_id = ? AND team_id = ?",
                (user_id, int(team["id"])),
            )
            mem = row_to_dict(mem_row) or {}
            role = str(mem.get("role") or "").strip() or "admin"
            active_team = {"id": team["id"], "name": team["name"], "role": role}
        else:
            mem_row = await fetchone(
                db,
                """
                SELECT t.id AS id, t.name AS name, m.role AS role
                FROM memberships m
                JOIN teams t ON t.id = m.team_id
                WHERE m.user_id = ?
                ORDER BY t.id ASC
                LIMIT 1
                """,
                (user_id,),
            )
            active_team = row_to_dict(mem_row)
            if not active_team:
                raise HTTPException(status_code=403, detail="该账号未加入任何团队")

    if is_super:
        teams_rows = await fetchall(
            db,
            """
            SELECT t.id AS id, t.name AS name, m.role AS role
            FROM teams t
            LEFT JOIN memberships m ON m.team_id = t.id AND m.user_id = ?
            ORDER BY t.id ASC
            """,
            (user_id,),
        )
        teams: list[dict] = []
        for row in rows_to_dicts(list(teams_rows)):
            role = str(row.get("role") or "").strip() or "admin"
            teams.append({"id": int(row["id"]), "name": str(row["name"]), "role": role})
    else:
        teams_rows = await fetchall(
            db,
            """
            SELECT t.id AS id, t.name AS name, m.role AS role
            FROM memberships m
            JOIN teams t ON t.id = m.team_id
            WHERE m.user_id = ?
            ORDER BY t.id ASC
            """,
            (user_id,),
        )
        teams = rows_to_dicts(list(teams_rows))

    token = create_access_token(
        settings=settings,
        user_id=user_id,
        email=str(user["email"]),
        team_id=int(active_team["id"]),
        team_role=str(active_team["role"] or "member"),
    )

    user_out = {"id": user_id, "email": str(user["email"]), "name": str(user["name"])}
    return AuthResponse(access_token=token, user=user_out, teams=teams, active_team=active_team)


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


class RegisterRequest(BaseModel):
    invite_token: str = Field(min_length=1, max_length=200)
    team_id: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=60)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


@router.post("/auth/register", response_model=AuthResponse)
async def register(req: RegisterRequest, settings=Depends(get_settings), db=Depends(get_db)) -> AuthResponse:  # noqa: ANN001
    token_in = req.invite_token.strip()
    if not token_in:
        raise HTTPException(status_code=400, detail="邀请码不能为空")

    now_iso = utc_now_iso()
    now_dt = datetime.now(tz=UTC)
    email = str(req.email).strip().lower()
    name = req.name.strip()

    shared_token = (settings.shared_invite_token or "").strip()
    if shared_token and token_in == shared_token:
        shared_team_id_raw = env_str("SHARED_INVITE_TEAM_ID", "") or ""
        shared_team_name = env_str("SHARED_INVITE_TEAM_NAME", "") or ""

        team_id: int | None = None
        if shared_team_id_raw:
            try:
                team_id = int(shared_team_id_raw)
            except Exception:
                team_id = None
        elif shared_team_name:
            row = await fetchone(
                db,
                "SELECT id FROM teams WHERE name = ? ORDER BY id ASC LIMIT 1",
                (shared_team_name,),
            )
            data = row_to_dict(row)
            if data:
                team_id = int(data.get("id") or 0) or None

        if team_id is None:
            if req.team_id is None:
                raise HTTPException(status_code=400, detail="请选择团队")
            team_id = int(req.team_id)
        else:
            if req.team_id is not None and int(req.team_id) != int(team_id):
                raise HTTPException(status_code=400, detail="通用邀请码不属于所选团队")

        role = (env_str("SHARED_INVITE_ROLE", "member") or "member").strip().lower() or "member"
        if role not in {"admin", "member"}:
            role = "member"
        if role == "admin" and (env_str("SHARED_INVITE_ALLOW_ADMIN", "") or "").strip() != "1":
            role = "member"

        await db.execute("BEGIN")
        try:
            team_row = await fetchone(db, "SELECT id, name FROM teams WHERE id = ?", (int(team_id),))
            team = row_to_dict(team_row)
            if not team:
                raise HTTPException(status_code=404, detail="团队不存在")

            existing_user_row = await fetchone(db, "SELECT id FROM users WHERE email = ?", (email,))
            if row_to_dict(existing_user_row):
                raise HTTPException(status_code=400, detail="该邮箱已注册，请直接登录")

            pwd_hash = hash_password(req.password)
            cur = await db.execute(
                "INSERT INTO users(email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (email, name, pwd_hash, now_iso),
            )
            user_id = int(cur.lastrowid)

            await db.execute(
                "INSERT INTO memberships(user_id, team_id, role, created_at) VALUES (?, ?, ?, ?)",
                (user_id, int(team_id), role, now_iso),
            )

            await db.commit()
        except HTTPException:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail=str(e)) from e

        teams = [{"id": int(team["id"]), "name": str(team.get("name") or "团队"), "role": role}]
        active_team = teams[0]
        access_token = create_access_token(
            settings=settings,
            user_id=user_id,
            email=email,
            team_id=int(team_id),
            team_role=role,
        )
        user_out = {"id": user_id, "email": email, "name": name}
        return AuthResponse(access_token=access_token, user=user_out, teams=teams, active_team=active_team)

    await db.execute("BEGIN")
    try:
        invite_row = await fetchone(
            db,
            """
            SELECT id, team_id, email, role, created_at, expires_at, used_at, used_by
            FROM invites
            WHERE token = ?
            """,
            (token_in,),
        )
        invite = row_to_dict(invite_row)
        if not invite:
            raise HTTPException(status_code=400, detail="邀请码不存在或已失效")
        if invite.get("used_at"):
            raise HTTPException(status_code=400, detail="邀请码已被使用")

        expires_at = str(invite.get("expires_at") or "")
        if not expires_at:
            raise HTTPException(status_code=400, detail="邀请码已失效")
        if _parse_dt(expires_at) < now_dt:
            raise HTTPException(status_code=400, detail="邀请码已过期")

        locked_email = str(invite.get("email") or "").strip().lower()
        if locked_email and locked_email != email:
            raise HTTPException(status_code=400, detail="邀请码绑定的邮箱不匹配")

        team_id = int(invite["team_id"])
        if req.team_id is not None and int(req.team_id) != team_id:
            raise HTTPException(status_code=400, detail="邀请码不属于所选团队")
        role = str(invite.get("role") or "member").strip().lower()
        if role not in {"admin", "member"}:
            role = "member"

        existing_user_row = await fetchone(db, "SELECT id FROM users WHERE email = ?", (email,))
        if row_to_dict(existing_user_row):
            raise HTTPException(status_code=400, detail="该邮箱已注册，请直接登录")

        pwd_hash = hash_password(req.password)
        cur = await db.execute(
            "INSERT INTO users(email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (email, name, pwd_hash, now_iso),
        )
        user_id = int(cur.lastrowid)

        await db.execute(
            "INSERT INTO memberships(user_id, team_id, role, created_at) VALUES (?, ?, ?, ?)",
            (user_id, team_id, role, now_iso),
        )

        cur = await db.execute(
            "UPDATE invites SET used_at = ?, used_by = ? WHERE id = ? AND used_at IS NULL",
            (now_iso, user_id, int(invite["id"])),
        )
        if cur.rowcount != 1:
            raise HTTPException(status_code=400, detail="邀请码已被使用")

        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e

    team_row = await fetchone(db, "SELECT id, name FROM teams WHERE id = ?", (team_id,))
    team = row_to_dict(team_row) or {"id": team_id, "name": "团队"}

    teams = [{"id": int(team["id"]), "name": str(team.get("name") or "团队"), "role": role}]
    active_team = teams[0]
    access_token = create_access_token(settings=settings, user_id=user_id, email=email, team_id=team_id, team_role=role)
    user_out = {"id": user_id, "email": email, "name": name}
    return AuthResponse(access_token=access_token, user=user_out, teams=teams, active_team=active_team)


class MeResponse(BaseModel):
    user: dict
    teams: list[dict]
    active_team: dict


@router.get("/me", response_model=MeResponse)
async def me(
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
    settings=Depends(get_settings),  # noqa: ANN001
) -> MeResponse:
    is_super = str(user.email).strip().lower() in settings.super_emails
    if is_super:
        teams_rows = await fetchall(
            db,
            """
            SELECT t.id AS id, t.name AS name, m.role AS role
            FROM teams t
            LEFT JOIN memberships m ON m.team_id = t.id AND m.user_id = ?
            ORDER BY t.id ASC
            """,
            (user.id,),
        )
        teams: list[dict] = []
        for row in rows_to_dicts(list(teams_rows)):
            role = str(row.get("role") or "").strip() or "admin"
            teams.append({"id": int(row["id"]), "name": str(row["name"]), "role": role})
    else:
        teams_rows = await fetchall(
            db,
            """
            SELECT t.id AS id, t.name AS name, m.role AS role
            FROM memberships m
            JOIN teams t ON t.id = m.team_id
            WHERE m.user_id = ?
            ORDER BY t.id ASC
            """,
            (user.id,),
        )
        teams = rows_to_dicts(list(teams_rows))
    active = {"id": user.team_id, "name": user.team_name, "role": user.team_role}
    return MeResponse(user={"id": user.id, "email": user.email, "name": user.name}, teams=teams, active_team=active)


class SwitchTeamRequest(BaseModel):
    team_id: int


@router.post("/auth/switch-team", response_model=AuthResponse)
async def switch_team(
    req: SwitchTeamRequest,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> AuthResponse:
    is_super = str(user.email).strip().lower() in settings.super_emails

    mem_row = await fetchone(
        db,
        """
        SELECT t.id AS id, t.name AS name, m.role AS role
        FROM memberships m
        JOIN teams t ON t.id = m.team_id
        WHERE m.user_id = ? AND m.team_id = ?
        """,
        (user.id, int(req.team_id)),
    )
    active_team = row_to_dict(mem_row)
    if not active_team and is_super:
        team_row = await fetchone(db, "SELECT id, name FROM teams WHERE id = ?", (int(req.team_id),))
        team = row_to_dict(team_row)
        if team:
            active_team = {"id": team["id"], "name": team["name"], "role": "admin"}
    if not active_team:
        raise HTTPException(status_code=403, detail="你不属于该团队")

    if is_super:
        teams_rows = await fetchall(
            db,
            """
            SELECT t.id AS id, t.name AS name, m.role AS role
            FROM teams t
            LEFT JOIN memberships m ON m.team_id = t.id AND m.user_id = ?
            ORDER BY t.id ASC
            """,
            (user.id,),
        )
        teams: list[dict] = []
        for row in rows_to_dicts(list(teams_rows)):
            role = str(row.get("role") or "").strip() or "admin"
            teams.append({"id": int(row["id"]), "name": str(row["name"]), "role": role})
    else:
        teams_rows = await fetchall(
            db,
            """
            SELECT t.id AS id, t.name AS name, m.role AS role
            FROM memberships m
            JOIN teams t ON t.id = m.team_id
            WHERE m.user_id = ?
            ORDER BY t.id ASC
            """,
            (user.id,),
        )
        teams = rows_to_dicts(list(teams_rows))

    token = create_access_token(
        settings=settings,
        user_id=user.id,
        email=user.email,
        team_id=int(active_team["id"]),
        team_role=str(active_team["role"] or "member"),
    )
    user_out = {"id": user.id, "email": user.email, "name": user.name}
    return AuthResponse(access_token=token, user=user_out, teams=teams, active_team=active_team)
