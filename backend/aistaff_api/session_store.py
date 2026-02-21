from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from .agent.types import ChatMessage


@dataclass
class SessionState:
    session_id: str
    user_id: int
    team_id: int
    role: str
    workspace_root: str
    created_at: float
    last_seen_at: float
    messages: list[ChatMessage]
    opencode_session_id: str | None = None
    codex_thread_id: str | None = None


def _estimate_chars(m: ChatMessage) -> int:
    content_len = len(m.content or "")
    # Attachments metadata is small; count it roughly.
    att_len = 0
    if m.attachments:
        try:
            att_len = sum(len(str(a.get("file_id") or "")) + len(str(a.get("filename") or "")) for a in m.attachments if isinstance(a, dict))  # type: ignore[arg-type]
        except Exception:
            att_len = 0
    return content_len + att_len + 32


def _trim_messages(messages: list[ChatMessage], max_messages: int, max_chars: int) -> list[ChatMessage]:
    if max_messages <= 0 or len(messages) <= max_messages:
        trimmed_by_count = messages
    else:
        system_msgs = [m for m in messages if m.role == "system"]
        rest = [m for m in messages if m.role != "system"]

        remaining = max_messages - len(system_msgs)
        if remaining <= 0:
            trimmed_by_count = system_msgs[:max_messages]
        else:
            trimmed_by_count = [*system_msgs, *rest[-remaining:]]

    if max_chars <= 0:
        return trimmed_by_count

    system_msgs = [m for m in trimmed_by_count if m.role == "system"]
    rest = [m for m in trimmed_by_count if m.role != "system"]

    kept: list[ChatMessage] = []
    total = 0
    # Keep the most recent messages within the budget.
    for m in reversed(rest):
        est = _estimate_chars(m)
        if kept and (total + est) > max_chars:
            break
        kept.append(m)
        total += est
    kept.reverse()
    return [*system_msgs, *kept]


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._lock = asyncio.Lock()

    def _is_expired(self, st: SessionState, ttl_seconds: int, now: float) -> bool:
        if ttl_seconds <= 0:
            return False
        return (now - st.last_seen_at) > ttl_seconds

    def _prune_locked(self, *, ttl_seconds: int, max_sessions: int, now: float) -> None:
        if ttl_seconds > 0:
            expired = [sid for sid, st in self._sessions.items() if self._is_expired(st, ttl_seconds, now)]
            for sid in expired:
                self._sessions.pop(sid, None)

        if max_sessions > 0 and len(self._sessions) > max_sessions:
            # Evict least-recently-seen sessions
            by_last_seen = sorted(self._sessions.items(), key=lambda kv: kv[1].last_seen_at)
            for sid, _st in by_last_seen[: max(0, len(self._sessions) - max_sessions)]:
                self._sessions.pop(sid, None)

    async def get_or_create(
        self,
        *,
        session_id: str,
        user_id: int,
        team_id: int,
        role: str,
        system_prompt: str,
        workspace_root: str,
        ttl_seconds: int,
        max_sessions: int,
    ) -> SessionState:
        now = time.time()
        async with self._lock:
            self._prune_locked(ttl_seconds=ttl_seconds, max_sessions=max_sessions, now=now)

            existing = self._sessions.get(session_id)
            if existing and self._is_expired(existing, ttl_seconds, now):
                self._sessions.pop(session_id, None)
                existing = None

            if existing:
                if existing.user_id != user_id or existing.team_id != team_id:
                    raise ValueError("session_id is not owned by current user/team")
                if existing.role != role or existing.workspace_root != workspace_root:
                    existing.role = role
                    existing.workspace_root = workspace_root
                    existing.opencode_session_id = None
                    existing.codex_thread_id = None
                    existing.messages = [ChatMessage(role="system", content=system_prompt)]
                elif existing.messages and existing.messages[0].role == "system":
                    existing.messages[0].content = system_prompt
                existing.last_seen_at = now
                return existing

            st = SessionState(
                session_id=session_id,
                user_id=user_id,
                team_id=team_id,
                role=role,
                workspace_root=workspace_root,
                created_at=now,
                last_seen_at=now,
                messages=[ChatMessage(role="system", content=system_prompt)],
                opencode_session_id=None,
            )
            self._sessions[session_id] = st
            self._prune_locked(ttl_seconds=ttl_seconds, max_sessions=max_sessions, now=now)
            return st

    async def update_messages(
        self,
        *,
        session_id: str,
        user_id: int,
        team_id: int,
        messages: list[ChatMessage],
        max_messages: int,
        max_chars: int,
    ) -> None:
        now = time.time()
        async with self._lock:
            st = self._sessions.get(session_id)
            if not st:
                return
            if st.user_id != user_id or st.team_id != team_id:
                return
            st.messages = _trim_messages(messages, max_messages=max_messages, max_chars=max_chars)
            st.last_seen_at = now

    async def assert_access(self, *, session_id: str, user_id: int, team_id: int, ttl_seconds: int) -> None:
        now = time.time()
        async with self._lock:
            st = self._sessions.get(session_id)
            if not st:
                raise ValueError("session not found")
            if self._is_expired(st, ttl_seconds, now):
                self._sessions.pop(session_id, None)
                raise ValueError("session expired")
            if st.user_id != user_id or st.team_id != team_id:
                raise ValueError("session_id is not owned by current user/team")
            st.last_seen_at = now


_STORE: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _STORE
    if _STORE is None:
        _STORE = SessionStore()
    return _STORE
