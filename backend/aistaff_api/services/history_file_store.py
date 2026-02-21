from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import Settings
from ..db import fetchall, fetchone, row_to_dict, rows_to_dicts, utc_now_iso

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _safe_session_id(session_id: str) -> str:
    value = str(session_id or "").strip()
    if not value or not _SESSION_ID_RE.match(value):
        raise ValueError("invalid session id")
    return value


def history_snapshots_root(settings: Settings) -> Path:
    return settings.db_path.parent / "history_sessions"


def history_user_dir(settings: Settings, team_id: int, user_id: int) -> Path:
    return history_snapshots_root(settings) / f"team-{int(team_id)}" / f"user-{int(user_id)}"


def session_snapshot_path(settings: Settings, team_id: int, user_id: int, session_id: str) -> Path:
    sid = _safe_session_id(session_id)
    return history_user_dir(settings, team_id, user_id) / f"{sid}.json"


def delete_session_snapshot(settings: Settings, team_id: int, user_id: int, session_id: str) -> None:
    try:
        path = session_snapshot_path(settings, team_id, user_id, session_id)
    except Exception:
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        return


def _safe_load_list(value: object) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except Exception:
            return []
        return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
    return []


async def sync_session_snapshot_from_db(
    *,
    settings: Settings,
    db,  # noqa: ANN001
    team_id: int,
    user_id: int,
    session_id: str,
) -> bool:
    sid = _safe_session_id(session_id)

    sess_row = await fetchone(
        db,
        """
        SELECT
          s.session_id,
          s.title,
          s.role,
          s.provider,
          s.model,
          s.project_id,
          s.created_at,
          s.updated_at,
          (
            SELECT m.content
            FROM chat_messages m
            WHERE m.session_id = s.session_id
            ORDER BY m.id DESC
            LIMIT 1
          ) AS last_message
        FROM chat_sessions s
        WHERE s.session_id = ? AND s.team_id = ? AND s.user_id = ?
        """,
        (sid, int(team_id), int(user_id)),
    )
    sess = row_to_dict(sess_row)
    if not sess:
        delete_session_snapshot(settings, team_id, user_id, sid)
        return False

    msg_rows = await fetchall(
        db,
        """
        SELECT id, role, content, attachments_json, events_json, created_at
        FROM chat_messages
        WHERE session_id = ? AND team_id = ? AND user_id = ?
        ORDER BY id ASC
        """,
        (sid, int(team_id), int(user_id)),
    )

    messages: list[dict] = []
    for row in rows_to_dicts(list(msg_rows)):
        events = None
        events_raw = row.get("events_json")
        if events_raw:
            try:
                events = json.loads(str(events_raw))
            except Exception:
                events = None

        messages.append(
            {
                "id": int(row.get("id") or 0),
                "role": str(row.get("role") or ""),
                "content": str(row.get("content") or ""),
                "created_at": str(row.get("created_at") or ""),
                "attachments": _safe_load_list(row.get("attachments_json")),
                "events": events,
            }
        )

    payload = {
        "schema": "aistaff.history.session.v1",
        "synced_at": utc_now_iso(),
        "team_id": int(team_id),
        "user_id": int(user_id),
        "session": {
            "session_id": str(sess.get("session_id") or sid),
            "title": str(sess.get("title") or ""),
            "role": str(sess.get("role") or "general"),
            "provider": str(sess.get("provider") or ""),
            "model": str(sess.get("model") or ""),
            "project_id": sess.get("project_id"),
            "created_at": str(sess.get("created_at") or ""),
            "updated_at": str(sess.get("updated_at") or ""),
            "last_message": str(sess.get("last_message") or "") if sess.get("last_message") is not None else None,
        },
        "messages": messages,
    }

    target = session_snapshot_path(settings, team_id, user_id, sid)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    return True


async def sync_recent_session_snapshots_from_db(
    *,
    settings: Settings,
    db,  # noqa: ANN001
    team_id: int,
    user_id: int,
    limit: int = 200,
) -> int:
    max_rows = max(1, min(int(limit), 1000))
    rows = await fetchall(
        db,
        """
        SELECT session_id
        FROM chat_sessions
        WHERE team_id = ? AND user_id = ?
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (int(team_id), int(user_id), max_rows),
    )

    synced = 0
    for item in rows_to_dicts(list(rows)):
        sid = str(item.get("session_id") or "").strip()
        if not sid:
            continue
        try:
            ok = await sync_session_snapshot_from_db(
                settings=settings,
                db=db,
                team_id=int(team_id),
                user_id=int(user_id),
                session_id=sid,
            )
            if ok:
                synced += 1
        except Exception:
            continue

    return synced
