from __future__ import annotations

from typing import Any

import httpx


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 14)] + "\n…(truncated)"


class FeishuWebhookService:
    def __init__(self, *, timeout_seconds: int = 20) -> None:
        self._timeout = max(3, int(timeout_seconds))

    async def send_text(self, *, webhook_url: str, content: str) -> None:
        url = str(webhook_url or "").strip()
        if not url:
            raise ValueError("Feishu webhook url is empty")

        text = str(content or "").strip()
        if not text:
            return

        payload = {
            "msg_type": "text",
            "content": {
                "text": _truncate(text, 4000),
            },
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            res = await client.post(url, json=payload)

        if res.status_code >= 400:
            raise ValueError(f"Feishu webhook failed: HTTP {res.status_code}: {res.text[:400]}")

        data: dict[str, Any] | None = None
        try:
            parsed = res.json()
            if isinstance(parsed, dict):
                data = parsed
        except Exception:
            data = None

        if not data:
            return

        if isinstance(data.get("code"), int) and int(data.get("code") or 0) != 0:
            raise ValueError(f"Feishu webhook error: {data.get('code')} {data.get('msg') or data.get('message')}")

        if isinstance(data.get("StatusCode"), int) and int(data.get("StatusCode") or 0) != 0:
            raise ValueError(f"Feishu webhook error: {data.get('StatusCode')} {data.get('StatusMessage')}")
