from __future__ import annotations

import base64
import asyncio
import time
from dataclasses import dataclass
from uuid import uuid4

from ..config import Settings
from ..output_cleanup import maybe_cleanup_outputs_dir
from ..url_utils import abs_url
from .auth_service import create_download_token


@dataclass
class _PageEntry:
    page: object
    last_seen_at: float


@dataclass
class _BrowserState:
    playwright: object | None = None
    browser: object | None = None
    pages: dict[str, _PageEntry] | None = None


_STATE = _BrowserState(playwright=None, browser=None, pages={})
_LOCK = asyncio.Lock()


class BrowserService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        maybe_cleanup_outputs_dir(
            self._settings.outputs_dir,
            ttl_seconds=max(0, int(self._settings.outputs_ttl_hours)) * 3600,
        )


    def _page_ttl_seconds(self) -> int:
        return max(0, int(self._settings.browser_page_ttl_minutes)) * 60

    def _max_pages(self) -> int:
        return max(0, int(self._settings.max_browser_pages))

    async def _ensure_enabled(self) -> None:
        if not self._settings.enable_browser:
            raise ValueError("Browser tools are disabled. Set AISTAFF_ENABLE_BROWSER=1.")

    async def _ensure_started(self) -> None:
        await self._ensure_enabled()
        async with _LOCK:
            if _STATE.playwright and _STATE.browser:
                return
            try:
                from playwright.async_api import async_playwright  # type: ignore
            except Exception as e:  # pragma: no cover
                raise RuntimeError("Playwright not installed. Run: uv sync --extra browser") from e

            _STATE.playwright = await async_playwright().start()
            _STATE.browser = await _STATE.playwright.chromium.launch(headless=True)  # type: ignore[attr-defined]

    async def _prune_pages_locked(self, *, now: float) -> None:
        if not _STATE.pages:
            _STATE.pages = {}
            return

        ttl_seconds = self._page_ttl_seconds()
        if ttl_seconds > 0:
            expired = [sid for sid, e in _STATE.pages.items() if (now - e.last_seen_at) > ttl_seconds]
            for sid in expired:
                entry = _STATE.pages.pop(sid, None)
                if not entry:
                    continue
                try:
                    await entry.page.close()  # type: ignore[union-attr]
                except Exception:
                    continue

        max_pages = self._max_pages()
        if max_pages > 0 and len(_STATE.pages) > max_pages:
            by_last_seen = sorted(_STATE.pages.items(), key=lambda kv: kv[1].last_seen_at)
            for sid, entry in by_last_seen[: max(0, len(_STATE.pages) - max_pages)]:
                _STATE.pages.pop(sid, None)
                try:
                    await entry.page.close()  # type: ignore[union-attr]
                except Exception:
                    continue

    async def start(self, session_id: str) -> object:
        await self._ensure_started()
        async with _LOCK:
            now = time.time()
            await self._prune_pages_locked(now=now)

            if not _STATE.pages:
                _STATE.pages = {}

            existing = _STATE.pages.get(session_id)
            if existing:
                existing.last_seen_at = now
                return existing.page

            max_pages = self._max_pages()
            if max_pages > 0 and len(_STATE.pages) >= max_pages:
                # Evict least-recently-used page to make room
                oldest_sid, oldest_entry = sorted(_STATE.pages.items(), key=lambda kv: kv[1].last_seen_at)[0]
                _STATE.pages.pop(oldest_sid, None)
                try:
                    await oldest_entry.page.close()  # type: ignore[union-attr]
                except Exception:
                    pass

            page = await _STATE.browser.new_page()  # type: ignore[union-attr]
            _STATE.pages[session_id] = _PageEntry(page=page, last_seen_at=now)
            return page

    async def navigate(self, session_id: str, url: str) -> None:
        page = await self.start(session_id)
        await page.goto(url, wait_until="domcontentloaded")  # type: ignore[union-attr]

    async def screenshot_base64(self, session_id: str) -> str:
        page = await self.start(session_id)
        img_bytes = await page.screenshot(type="png", full_page=True)  # type: ignore[union-attr]
        return base64.b64encode(img_bytes).decode("ascii")

    async def screenshot_file(self, session_id: str) -> dict:
        await self.start(session_id)
        img_b64 = await self.screenshot_base64(session_id)
        img_bytes = base64.b64decode(img_b64.encode("ascii"))

        self._settings.outputs_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid4().hex}.png"
        path = (self._settings.outputs_dir / filename).resolve()
        path.write_bytes(img_bytes)

        file_id = filename
        token = create_download_token(settings=self._settings, file_id=file_id)
        return {
            "file_id": file_id,
            "filename": filename,
            "download_url": abs_url(self._settings, f"/api/files/{file_id}?token={token}"),
        }
