from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_settings


router = APIRouter(tags=["meta"])


@router.get("/meta")
def meta(settings=Depends(get_settings)) -> dict:  # noqa: ANN001
    providers = ["openai", "codex", "opencode", "nanobot", "mock"]
    if bool(getattr(settings, "enable_pi", False)):
        providers.append("pi")
    return {
        "providers": providers,
        "pi": {
            "enabled": bool(getattr(settings, "enable_pi", False)),
            "backend": str(getattr(settings, "pi_backend", "auto")),
        },
    }

