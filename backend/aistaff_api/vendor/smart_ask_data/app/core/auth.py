from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request


@dataclass(frozen=True)
class User:
    username: str
    role: str
    allowed_datasource_ids: list[str]


def _pbkdf2_hash(password: str, salt: bytes, iterations: int = 120_000) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = _pbkdf2_hash(password, salt)
    return "pbkdf2_sha256$120000$" + base64.urlsafe_b64encode(salt + digest).decode("ascii")


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iter_str, payload = stored.split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        salt, digest = raw[:16], raw[16:]
        computed = _pbkdf2_hash(password, salt, iterations)
        return hmac.compare_digest(computed, digest)
    except Exception:
        return False


def get_session_user(request: Request) -> Optional[str]:
    user = request.session.get("user")
    if isinstance(user, str) and user:
        return user
    return None


def require_user(request: Request) -> str:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


def require_user_dep(user: str = Depends(require_user)) -> str:
    return user

