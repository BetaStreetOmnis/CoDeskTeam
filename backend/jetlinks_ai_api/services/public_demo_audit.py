from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any

from fastapi import Request


class PublicDemoAuditLogger:
    def __init__(self, *, enabled: bool, path: Path) -> None:
        self._enabled = bool(enabled)
        self._path = Path(path)
        self._lock = threading.Lock()

    def log(
        self,
        *,
        event: str,
        request: Request,
        status_code: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if not self._enabled:
            return

        record: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": str(event or "").strip() or "unknown",
            "method": str(request.method or "").upper(),
            "path": str(request.url.path or ""),
            "client_ip": self._client_ip(request),
            "user_agent": str(request.headers.get("user-agent") or "")[:300],
        }
        if status_code is not None:
            record["status_code"] = int(status_code)
        if extra:
            for key, value in extra.items():
                if value is None:
                    continue
                record[str(key)] = value

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(record, ensure_ascii=False)
            with self._lock:
                with self._path.open("a", encoding="utf-8") as fp:
                    fp.write(line)
                    fp.write("\n")
        except Exception:
            return

    @staticmethod
    def _client_ip(request: Request) -> str:
        forwarded_for = str(request.headers.get("x-forwarded-for") or "").strip()
        if forwarded_for:
            first = forwarded_for.split(",", 1)[0].strip()
            if first:
                return first
        real_ip = str(request.headers.get("x-real-ip") or "").strip()
        if real_ip:
            return real_ip
        client = getattr(request, "client", None)
        host = str(getattr(client, "host", "") or "").strip()
        return host or "unknown"
