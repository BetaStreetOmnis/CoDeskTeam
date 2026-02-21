from __future__ import annotations

from .config import Settings


def abs_url(settings: Settings, path_or_url: str) -> str:
    value = str(path_or_url or "").strip()
    if not value:
        return value
    if value.startswith(("http://", "https://")):
        return value

    base = (getattr(settings, "public_base_url", "") or "").strip().rstrip("/")
    if not base:
        return value

    path = value if value.startswith("/") else f"/{value}"
    return f"{base}{path}"
