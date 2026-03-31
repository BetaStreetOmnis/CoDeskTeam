from __future__ import annotations

from html import escape
from uuid import uuid4

from ...config import Settings
from ...output_cleanup import maybe_cleanup_outputs_dir
from ...url_utils import abs_url
from ..auth_service import create_download_token


class PosterDocService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._settings.outputs_dir.mkdir(parents=True, exist_ok=True)
        maybe_cleanup_outputs_dir(
            self._settings.outputs_dir,
            ttl_seconds=max(0, int(self._settings.outputs_ttl_hours)) * 3600,
        )

    async def create_poster_svg(
        self,
        *,
        title: str,
        subtitle: str | None = None,
        bullets: list[str] | None = None,
        footer: str | None = None,
        theme: str | None = None,
        width: int = 1600,
        height: int = 2400,
    ) -> dict:
        safe_width = max(800, min(4000, int(width or 1600)))
        safe_height = max(1200, min(6000, int(height or 2400)))
        theme_name = str(theme or "aurora").strip().lower()
        palettes = {
            "aurora": {
                "bg1": "#081226",
                "bg2": "#183b7a",
                "accent": "#7dd3fc",
                "text": "#f8fafc",
                "muted": "#cbd5e1",
                "card": "rgba(8, 18, 38, 0.56)",
            },
            "sunset": {
                "bg1": "#3b0764",
                "bg2": "#ea580c",
                "accent": "#fdba74",
                "text": "#fff7ed",
                "muted": "#fed7aa",
                "card": "rgba(88, 28, 135, 0.48)",
            },
            "forest": {
                "bg1": "#052e16",
                "bg2": "#166534",
                "accent": "#86efac",
                "text": "#f0fdf4",
                "muted": "#bbf7d0",
                "card": "rgba(5, 46, 22, 0.52)",
            },
        }
        palette = palettes.get(theme_name, palettes["aurora"])
        items = [str(item or "").strip() for item in (bullets or []) if str(item or "").strip()][:8]
        if not items:
            items = ["补充一句业务亮点", "补充一句能力优势", "补充一句落地价值"]

        title_y = int(safe_height * 0.16)
        subtitle_y = title_y + 120
        card_x = 110
        card_y = int(safe_height * 0.28)
        card_w = safe_width - 220
        card_h = safe_height - card_y - 180
        bullet_start_y = card_y + 190
        bullet_gap = max(100, int((card_h - 260) / max(1, len(items))))

        def t(text: str) -> str:
            return escape(str(text or ""), quote=False)

        bullet_svg = []
        for idx, item in enumerate(items):
            y = bullet_start_y + idx * bullet_gap
            bullet_svg.append(
                f'''<circle cx="{card_x + 72}" cy="{y - 12}" r="12" fill="{palette['accent']}" opacity="0.95" />'''
            )
            bullet_svg.append(
                f'''<text x="{card_x + 108}" y="{y}" fill="{palette['text']}" font-size="46" font-family="Inter, PingFang SC, Microsoft YaHei, sans-serif">{t(item)}</text>'''
            )

        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{safe_width}" height="{safe_height}" viewBox="0 0 {safe_width} {safe_height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{palette['bg1']}" />
      <stop offset="100%" stop-color="{palette['bg2']}" />
    </linearGradient>
    <filter id="blur"><feGaussianBlur stdDeviation="90" /></filter>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)" />
  <circle cx="{int(safe_width * 0.18)}" cy="{int(safe_height * 0.14)}" r="220" fill="{palette['accent']}" opacity="0.20" filter="url(#blur)" />
  <circle cx="{int(safe_width * 0.82)}" cy="{int(safe_height * 0.82)}" r="280" fill="#ffffff" opacity="0.10" filter="url(#blur)" />
  <text x="110" y="{title_y}" fill="{palette['text']}" font-size="108" font-weight="700" font-family="Inter, PingFang SC, Microsoft YaHei, sans-serif">{t(title)}</text>
  <text x="114" y="{subtitle_y}" fill="{palette['muted']}" font-size="44" font-family="Inter, PingFang SC, Microsoft YaHei, sans-serif">{t(subtitle or '')}</text>
  <rect x="{card_x}" y="{card_y}" width="{card_w}" height="{card_h}" rx="48" fill="{palette['card']}" stroke="rgba(255,255,255,0.20)" />
  <text x="{card_x + 54}" y="{card_y + 92}" fill="{palette['accent']}" font-size="34" letter-spacing="4" font-family="Inter, PingFang SC, Microsoft YaHei, sans-serif">KEY POINTS</text>
  {''.join(bullet_svg)}
  <text x="110" y="{safe_height - 66}" fill="{palette['muted']}" font-size="30" font-family="Inter, PingFang SC, Microsoft YaHei, sans-serif">{t(footer or '')}</text>
</svg>
'''
        file_id = f"{uuid4().hex}.svg"
        path = (self._settings.outputs_dir / file_id).resolve()
        path.write_text(svg, encoding="utf-8")
        token = create_download_token(settings=self._settings, file_id=file_id)
        return {
            "file_id": file_id,
            "filename": file_id,
            "download_url": abs_url(self._settings, f"/api/files/{file_id}?token={token}"),
            "content_type": "image/svg+xml",
            "width": safe_width,
            "height": safe_height,
            "theme": theme_name,
        }
