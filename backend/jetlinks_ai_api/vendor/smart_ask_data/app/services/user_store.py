from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.auth import hash_password, verify_password
from app.services.datasource_store import validate_identifier


def _default_store_path() -> Path:
    env = os.getenv("SMARTASK_USER_STORE_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "storage" / "users.json"


_DEFAULT_USERS: list[dict[str, Any]] = [
    {
        "username": "admin",
        "password_hash": hash_password("admin123"),
        "role": "admin",
        "allowed_datasource_ids": ["*"],
    }
]


@dataclass(frozen=True)
class UserRecord:
    username: str
    password_hash: str
    role: str
    allowed_datasource_ids: list[str]


class UserStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_store_path()
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {"users": []}
        self._load()

    def _load(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._data = {"users": list(_DEFAULT_USERS)}
            self._save()
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw or "{}")
            if isinstance(data, dict) and isinstance(data.get("users"), list):
                self._data = data
            else:
                self._data = {"users": []}
        except Exception:
            self._data = {"users": []}
        self._ensure_default()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def _ensure_default(self) -> None:
        with self._lock:
            users = self._data.setdefault("users", [])
            has_admin = any(u.get("role") == "admin" for u in users)
            if not users or not has_admin:
                users.extend(list(_DEFAULT_USERS))
                self._save()

    def _normalize_allowed(self, allowed: list[str] | None) -> list[str]:
        items = [str(i).strip() for i in (allowed or []) if str(i).strip()]
        return items or ["*"]

    def list_users(self) -> list[UserRecord]:
        with self._lock:
            items = list(self._data.get("users") or [])
        return [
            UserRecord(
                username=str(u.get("username") or ""),
                password_hash=str(u.get("password_hash") or ""),
                role=str(u.get("role") or "user"),
                allowed_datasource_ids=list(u.get("allowed_datasource_ids") or ["*"]),
            )
            for u in items
            if str(u.get("username") or "")
        ]

    def get_user(self, username: str) -> UserRecord | None:
        key = (username or "").strip()
        if not key:
            return None
        for u in self.list_users():
            if u.username == key:
                return u
        return None

    def verify_user(self, username: str, password: str) -> UserRecord | None:
        user = self.get_user(username)
        if not user:
            return None
        if verify_password(password, user.password_hash):
            return user
        return None

    def count_admins(self) -> int:
        return sum(1 for u in self.list_users() if u.role == "admin")

    def create_user(
        self,
        username: str,
        password: str,
        *,
        role: str = "user",
        allowed_datasource_ids: list[str] | None = None,
    ) -> UserRecord:
        name = validate_identifier(username, "用户名")
        if self.get_user(name):
            raise ValueError("用户名已存在")
        if not password:
            raise ValueError("密码不能为空")
        record = {
            "username": name,
            "password_hash": hash_password(password),
            "role": (role or "user").strip() or "user",
            "allowed_datasource_ids": self._normalize_allowed(allowed_datasource_ids),
        }
        with self._lock:
            users = self._data.setdefault("users", [])
            users.append(record)
            self._save()
        return UserRecord(**record)

    def update_user(
        self,
        username: str,
        *,
        password: str | None = None,
        role: str | None = None,
        allowed_datasource_ids: list[str] | None = None,
    ) -> UserRecord | None:
        name = (username or "").strip()
        if not name:
            return None
        updated: dict[str, Any] | None = None
        with self._lock:
            users = self._data.setdefault("users", [])
            for item in users:
                if item.get("username") == name:
                    if password:
                        item["password_hash"] = hash_password(password)
                    if role is not None:
                        item["role"] = (role or "user").strip() or "user"
                    if allowed_datasource_ids is not None:
                        item["allowed_datasource_ids"] = self._normalize_allowed(allowed_datasource_ids)
                    updated = dict(item)
                    self._save()
                    break
        return UserRecord(**updated) if updated else None

    def delete_user(self, username: str) -> bool:
        name = (username or "").strip()
        if not name:
            return False
        with self._lock:
            users = self._data.setdefault("users", [])
            before = len(users)
            users[:] = [u for u in users if u.get("username") != name]
            changed = len(users) != before
            if changed:
                self._save()
            return changed


user_store = UserStore()
