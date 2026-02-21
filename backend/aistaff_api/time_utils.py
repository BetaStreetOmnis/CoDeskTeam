from __future__ import annotations

from datetime import datetime, timezone

try:  # Python 3.11+
    from datetime import UTC  # type: ignore
except ImportError:  # Python 3.10 fallback
    UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat()
