from __future__ import annotations

import os


PRIMARY_PREFIX = "JETLINKS_AI_"
LEGACY_PREFIX = "AISTAFF_"


def _prefixed_names(suffix: str) -> tuple[str, str]:
    s = (suffix or "").strip().upper()
    if not s:
        raise ValueError("empty env suffix")
    return (f"{PRIMARY_PREFIX}{s}", f"{LEGACY_PREFIX}{s}")


def env_str(suffix: str, default: str | None = None) -> str | None:
    for name in _prefixed_names(suffix):
        value = os.getenv(name)
        if value is None:
            continue
        value = value.strip()
        return value if value else default
    return default


def env_bool(suffix: str, default: bool) -> bool:
    raw = env_str(suffix, None)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def env_int(suffix: str, default: int) -> int:
    raw = env_str(suffix, None)
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        return default

