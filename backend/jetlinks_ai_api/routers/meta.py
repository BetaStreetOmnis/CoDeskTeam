from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends

from ..deps import get_settings


router = APIRouter(tags=["meta"])


@router.get("/meta")
def meta(settings=Depends(get_settings)) -> dict:  # noqa: ANN001
    providers = ["openai", "codex", "opencode", "nanobot", "mock"]
    openclaw_enabled = bool(getattr(settings, "openclaw_enabled", True))
    if openclaw_enabled:
        providers.append("openclaw")
    claude_cmd = str(getattr(settings, "claude_command", "") or "").strip()
    if claude_cmd and shutil.which(claude_cmd):
        providers.append("claude")
    if bool(getattr(settings, "glm_api_key", None)):
        providers.append("glm")
    if bool(getattr(settings, "enable_pi", False)):
        providers.append("pi")
    return {
        "providers": providers,
        "pi": {
            "enabled": bool(getattr(settings, "enable_pi", False)),
            "backend": str(getattr(settings, "pi_backend", "auto")),
        },
    }
