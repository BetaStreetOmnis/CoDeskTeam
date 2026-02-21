from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import jwt
from passlib.context import CryptContext

from ..config import Settings
from ..time_utils import UTC


# NOTE:
# passlib+bcrypt 在部分环境下会在 backend 自检阶段触发 "password cannot be longer than 72 bytes" 异常，
# 导致首次 setup/login 直接 500。为了稳定性，这里使用不依赖 bcrypt backend 的 pbkdf2_sha256。
_pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


@dataclass(frozen=True)
class TokenData:
    user_id: int
    email: str
    team_id: int
    team_role: str


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def _now_ts() -> int:
    return int(datetime.now(tz=UTC).timestamp())


def _encode(settings: Settings, payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode(settings: Settings, token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def create_access_token(*, settings: Settings, user_id: int, email: str, team_id: int, team_role: str) -> str:
    now = datetime.now(tz=UTC)
    exp = now + timedelta(minutes=settings.jwt_exp_minutes)
    payload: dict[str, Any] = {
        "scope": "user",
        "sub": str(user_id),
        "email": email,
        "tid": int(team_id),
        "trole": team_role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return _encode(settings, payload)


def decode_access_token(*, settings: Settings, token: str) -> TokenData:
    payload = _decode(settings, token)
    if payload.get("scope") != "user":
        raise ValueError("invalid token scope")
    sub = payload.get("sub")
    if not sub or not str(sub).isdigit():
        raise ValueError("invalid token sub")
    email = str(payload.get("email") or "").strip()
    if not email:
        raise ValueError("invalid token email")
    team_id = payload.get("tid")
    if team_id is None:
        raise ValueError("invalid token team id")
    team_role = str(payload.get("trole") or "").strip() or "member"
    return TokenData(user_id=int(sub), email=email, team_id=int(team_id), team_role=team_role)


def create_download_token(*, settings: Settings, file_id: str, expires_minutes: int = 7 * 24 * 60) -> str:
    now_ts = _now_ts()
    payload: dict[str, Any] = {
        "scope": "download",
        "fid": file_id,
        "iat": now_ts,
        "exp": now_ts + int(expires_minutes * 60),
    }
    return _encode(settings, payload)


def validate_download_token(*, settings: Settings, token: str, file_id: str) -> None:
    payload = _decode(settings, token)
    if payload.get("scope") != "download":
        raise ValueError("invalid download token scope")
    if str(payload.get("fid") or "") != file_id:
        raise ValueError("download token mismatch")
