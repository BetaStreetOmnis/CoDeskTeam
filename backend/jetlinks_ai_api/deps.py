from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, load_settings
from .db import fetchone, open_db, row_to_dict
from .services.auth_service import TokenData, decode_access_token


_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str
    name: str
    team_id: int
    team_name: str
    team_role: str


def get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, Settings):
        return settings
    return load_settings()

def _is_super(settings: Settings, email: str) -> bool:
    return str(email or "").strip().lower() in settings.super_emails


async def get_db(settings: Settings = Depends(get_settings)) -> AsyncIterator:
    async with open_db(settings) as db:
        yield db


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),  # noqa: ANN001
) -> CurrentUser:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="未登录")

    try:
        token = creds.credentials.strip()
        data: TokenData = decode_access_token(settings=settings, token=token)
    except Exception:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录") from None

    user_row = await fetchone(db, "SELECT id, email, name FROM users WHERE id = ?", (data.user_id,))
    user = row_to_dict(user_row)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    is_super = _is_super(settings, str(user.get("email") or ""))

    mem_row = await fetchone(
        db,
        """
        SELECT m.role AS team_role, t.id AS team_id, t.name AS team_name
        FROM memberships m
        JOIN teams t ON t.id = m.team_id
        WHERE m.user_id = ? AND m.team_id = ?
        """,
        (data.user_id, data.team_id),
    )
    mem = row_to_dict(mem_row)
    if not mem:
        if not is_super:
            raise HTTPException(status_code=401, detail="团队关系不存在")
        team_row = await fetchone(db, "SELECT id, name FROM teams WHERE id = ?", (data.team_id,))
        team = row_to_dict(team_row)
        if not team:
            raise HTTPException(status_code=401, detail="团队不存在")
        mem = {"team_id": team["id"], "team_name": team["name"], "team_role": "admin"}

    return CurrentUser(
        id=int(user["id"]),
        email=str(user["email"]),
        name=str(user["name"]),
        team_id=int(mem["team_id"]),
        team_name=str(mem["team_name"]),
        team_role=str(mem["team_role"] or "member"),
    )


async def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),  # noqa: ANN001
) -> CurrentUser | None:
    if creds is None or not creds.credentials:
        return None
    try:
        token = creds.credentials.strip()
        data: TokenData = decode_access_token(settings=settings, token=token)
    except Exception:
        return None

    user_row = await fetchone(db, "SELECT id, email, name FROM users WHERE id = ?", (data.user_id,))
    user = row_to_dict(user_row)
    if not user:
        return None

    is_super = _is_super(settings, str(user.get("email") or ""))

    mem_row = await fetchone(
        db,
        """
        SELECT m.role AS team_role, t.id AS team_id, t.name AS team_name
        FROM memberships m
        JOIN teams t ON t.id = m.team_id
        WHERE m.user_id = ? AND m.team_id = ?
        """,
        (data.user_id, data.team_id),
    )
    mem = row_to_dict(mem_row)
    if not mem:
        if not is_super:
            return None
        team_row = await fetchone(db, "SELECT id, name FROM teams WHERE id = ?", (data.team_id,))
        team = row_to_dict(team_row)
        if not team:
            return None
        mem = {"team_id": team["id"], "team_name": team["name"], "team_role": "admin"}

    return CurrentUser(
        id=int(user["id"]),
        email=str(user["email"]),
        name=str(user["name"]),
        team_id=int(mem["team_id"]),
        team_name=str(mem["team_name"]),
        team_role=str(mem["team_role"] or "member"),
    )


def require_team_admin(user: CurrentUser) -> None:
    if user.team_role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="需要团队管理员权限")
