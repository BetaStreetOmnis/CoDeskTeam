from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class _TokenEntry:
    access_token: str
    expires_at: float


_TOKEN_CACHE: dict[tuple[str, str], _TokenEntry] = {}
_LOCK = asyncio.Lock()


def _truncate(text: str, max_chars: int) -> str:
    s = (text or "").strip()
    if len(s) <= max_chars:
        return s
    return s[: max(0, max_chars - 14)] + "\n…(truncated)"


class WecomService:
    def __init__(self, *, base_url: str = "https://qyapi.weixin.qq.com") -> None:
        self._base_url = (base_url or "").strip().rstrip("/") or "https://qyapi.weixin.qq.com"

    async def get_access_token(self, *, corp_id: str, corp_secret: str) -> str:
        cid = (corp_id or "").strip()
        sec = (corp_secret or "").strip()
        if not cid:
            raise ValueError("corp_id is empty")
        if not sec:
            raise ValueError("corp_secret is empty")

        key = (cid, sec)
        now = time.time()
        async with _LOCK:
            cached = _TOKEN_CACHE.get(key)
            if cached and cached.access_token and (cached.expires_at - 60) > now:
                return cached.access_token

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            res = await client.get(
                f"{self._base_url}/cgi-bin/gettoken",
                params={"corpid": cid, "corpsecret": sec},
            )
            data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}

        if res.status_code >= 400:
            raise ValueError(f"WeCom gettoken failed: HTTP {res.status_code}: {res.text[:400]}")

        if not isinstance(data, dict):
            raise ValueError(f"WeCom gettoken invalid response: {res.text[:400]}")
        if int(data.get("errcode") or 0) != 0:
            raise ValueError(f"WeCom gettoken error: {data.get('errcode')} {data.get('errmsg')}")

        token = str(data.get("access_token") or "").strip()
        expires_in = int(data.get("expires_in") or 0)
        if not token:
            raise ValueError("WeCom gettoken missing access_token")

        async with _LOCK:
            _TOKEN_CACHE[key] = _TokenEntry(access_token=token, expires_at=now + max(1, expires_in))
        return token

    async def send_text(
        self,
        *,
        corp_id: str,
        corp_secret: str,
        agent_id: int,
        to_user: str | None = None,
        chat_id: str | None = None,
        content: str,
    ) -> dict[str, Any]:
        token = await self.get_access_token(corp_id=corp_id, corp_secret=corp_secret)
        text = _truncate(content, 1800)

        payload: dict[str, Any] = {
            "msgtype": "text",
            "agentid": int(agent_id),
            "text": {"content": text},
        }

        if chat_id and str(chat_id).strip():
            payload["chatid"] = str(chat_id).strip()
        else:
            uid = str(to_user or "").strip()
            if not uid:
                raise ValueError("missing to_user/chat_id")
            payload["touser"] = uid

        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            res = await client.post(
                f"{self._base_url}/cgi-bin/message/send",
                params={"access_token": token},
                json=payload,
            )
            data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}

        if res.status_code >= 400:
            raise ValueError(f"WeCom message/send failed: HTTP {res.status_code}: {res.text[:400]}")
        if not isinstance(data, dict):
            raise ValueError(f"WeCom message/send invalid response: {res.text[:400]}")
        if int(data.get("errcode") or 0) != 0:
            raise ValueError(f"WeCom message/send error: {data.get('errcode')} {data.get('errmsg')}")
        return data

