from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

import httpx


@dataclass
class _TokenEntry:
    access_token: str
    expires_at: float


_TOKEN_CACHE: dict[tuple[str, str], _TokenEntry] = {}
_LOCK = asyncio.Lock()

_FILENAME_RE = re.compile(r"filename\\*=UTF-8''([^;]+)|filename=\"?([^\";]+)\"?", re.IGNORECASE)


def _split_chunks(text: str, max_chars: int) -> list[str]:
    s = (text or "").strip()
    if not s:
        return []
    if max_chars <= 0 or len(s) <= max_chars:
        return [s]

    chunks: list[str] = []
    rest = s
    min_nl_cut = max(8, int(max_chars * 0.4))

    while rest:
        if len(rest) <= max_chars:
            chunks.append(rest.strip())
            break

        cut = rest.rfind("\n", 0, max_chars + 1)
        if cut < min_nl_cut:
            cut = max_chars
        chunk = rest[:cut].rstrip()
        chunks.append(chunk)
        rest = rest[cut:].lstrip()

    return [c for c in chunks if c]


class WecomService:
    def __init__(self, *, base_url: str = "https://qyapi.weixin.qq.com") -> None:
        self._base_url = (base_url or "").strip().rstrip("/") or "https://qyapi.weixin.qq.com"

    def _filename_from_headers(self, headers: dict[str, str] | None) -> str | None:
        if not headers:
            return None
        cd = str(headers.get("content-disposition") or headers.get("Content-Disposition") or "").strip()
        if not cd:
            return None
        m = _FILENAME_RE.search(cd)
        if not m:
            return None
        raw = m.group(1) or m.group(2) or ""
        raw = raw.strip().strip('"').strip("'")
        if not raw:
            return None
        try:
            return unquote(raw)
        except Exception:
            return raw

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

    async def download_media(
        self,
        *,
        corp_id: str,
        corp_secret: str,
        media_id: str,
    ) -> tuple[bytes, str, str | None]:
        token = await self.get_access_token(corp_id=corp_id, corp_secret=corp_secret)
        mid = (media_id or "").strip()
        if not mid:
            raise ValueError("media_id is empty")

        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0)) as client:
            res = await client.get(
                f"{self._base_url}/cgi-bin/media/get",
                params={"access_token": token, "media_id": mid},
            )

        ctype = str(res.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if ctype.startswith("application/json"):
            data = res.json() if res.text else {}
            if res.status_code >= 400:
                raise ValueError(f"WeCom media/get failed: HTTP {res.status_code}: {res.text[:400]}")
            if not isinstance(data, dict):
                raise ValueError(f"WeCom media/get invalid response: {res.text[:400]}")
            if int(data.get("errcode") or 0) != 0:
                raise ValueError(f"WeCom media/get error: {data.get('errcode')} {data.get('errmsg')}")
            raise ValueError("WeCom media/get returned json without media content")

        if res.status_code >= 400:
            raise ValueError(f"WeCom media/get failed: HTTP {res.status_code}: {res.text[:400]}")

        filename = self._filename_from_headers(dict(res.headers))
        content = res.content or b""
        return content, (ctype or "application/octet-stream"), filename

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
        max_chars = 1800
        # Reserve a bit for the "(i/n)" prefix when splitting.
        chunks = _split_chunks(content, max_chars=max_chars - 10)
        if len(chunks) > 1:
            total = len(chunks)
            chunks = [f"({i}/{total})\n{c}".strip() for i, c in enumerate(chunks, start=1)]
        if not chunks:
            raise ValueError("content is empty")

        base_payload: dict[str, Any] = {
            "msgtype": "text",
            "agentid": int(agent_id),
        }
        if chat_id and str(chat_id).strip():
            base_payload["chatid"] = str(chat_id).strip()
        else:
            uid = str(to_user or "").strip()
            if not uid:
                raise ValueError("missing to_user/chat_id")
            base_payload["touser"] = uid

        last_data: dict[str, Any] = {}
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            for idx, chunk in enumerate(chunks):
                payload = {**base_payload, "text": {"content": chunk}}
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
                last_data = data

                # Avoid triggering rate limits on long replies.
                if idx + 1 < len(chunks):
                    await asyncio.sleep(0.25)

        return last_data
