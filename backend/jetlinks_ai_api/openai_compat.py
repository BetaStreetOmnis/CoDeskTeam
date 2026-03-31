from __future__ import annotations

import re

_V1_RE = re.compile(r"/v1(?:$|/)")


def normalize_openai_base_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return base
    # GLM (BigModel) OpenAI-compatible endpoint uses /api/paas/v4 directly.
    # If we append /v1 here, requests become /v4/v1/* and will 404.
    if "open.bigmodel.cn/api/paas/v4" in base.lower():
        return base
    if _V1_RE.search(base):
        return base
    return f"{base}/v1"


def openai_base_candidates(base_url: str) -> list[str]:
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        return []
    candidates = [raw]
    normalized = normalize_openai_base_url(raw)
    if normalized and normalized not in candidates:
        candidates.append(normalized)
    return candidates
