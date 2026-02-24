from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import Request


@dataclass
class _UserState:
    results: dict[str, dict]
    pins: list[str]


class InMemoryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._users: dict[str, _UserState] = {}

    def _user_key(self, request: Request) -> str:
        user = request.session.get("user")
        return str(user) if user else "anonymous"

    def _ensure_user(self, key: str) -> _UserState:
        if key not in self._users:
            self._users[key] = _UserState(results={}, pins=[])
        return self._users[key]

    def save_result(self, request: Request, result: dict) -> str:
        key = self._user_key(request)
        with self._lock:
            state = self._ensure_user(key)
            rid = uuid4().hex
            state.results[rid] = result
            return rid

    def get_result(self, request: Request, result_id: str) -> dict | None:
        key = self._user_key(request)
        with self._lock:
            state = self._ensure_user(key)
            return state.results.get(result_id)

    def update_chart(self, request: Request, result_id: str, chart: dict) -> None:
        key = self._user_key(request)
        with self._lock:
            state = self._ensure_user(key)
            if result_id not in state.results:
                raise ValueError("result_id不存在")
            state.results[result_id]["chart"] = chart

    def pin(self, request: Request, result_id: str) -> None:
        key = self._user_key(request)
        with self._lock:
            state = self._ensure_user(key)
            if result_id not in state.results:
                raise ValueError("result_id不存在")
            if result_id not in state.pins:
                state.pins.append(result_id)

    def unpin(self, request: Request, result_id: str) -> None:
        key = self._user_key(request)
        with self._lock:
            state = self._ensure_user(key)
            state.pins = [rid for rid in state.pins if rid != result_id]

    def list_pins(self, request: Request) -> list[dict]:
        key = self._user_key(request)
        with self._lock:
            state = self._ensure_user(key)
            items: list[dict] = []
            for rid in state.pins:
                r = state.results.get(rid)
                if r:
                    items.append({"result_id": rid, **r})
            return items


store = InMemoryStore()
