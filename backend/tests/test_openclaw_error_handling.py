from __future__ import annotations

from jetlinks_ai_api.services.agent_service import _should_fallback_openclaw_error
from jetlinks_ai_api.services.openclaw_service import _is_transient_openclaw_error


def test_openclaw_transient_error_markers_cover_timeout_and_gateway() -> None:
    assert _is_transient_openclaw_error("OpenClaw timed out after 300s") is True
    assert _is_transient_openclaw_error("gateway closed unexpectedly") is True
    assert _is_transient_openclaw_error("connection error: ECONNRESET") is True
    assert _is_transient_openclaw_error("stop reason: sensitive") is False


def test_openclaw_fallback_error_markers_cover_timeout_and_auth() -> None:
    assert _should_fallback_openclaw_error("OpenClaw timed out after 300s") is True
    assert _should_fallback_openclaw_error("OpenClaw command failed (exit=1): gateway closed") is True
    assert _should_fallback_openclaw_error("模型鉴权失败") is True
    assert _should_fallback_openclaw_error("stop reason: sensitive") is False
