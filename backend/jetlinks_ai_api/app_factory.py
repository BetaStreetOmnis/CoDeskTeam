from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .db import init_db
from .env_utils import env_str
from .output_cleanup import cleanup_outputs_dir
from .routers import (
    admin_teams,
    auth,
    browser,
    chat,
    chatbi,
    docs,
    feishu,
    files,
    history,
    integrations_openclaw,
    meta,
    openai_proxy,
    prototype,
    skills,
    team,
    team_integrations,
    wecom,
)


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ANN001
        await init_db(settings)
        cleanup_outputs_dir(settings.outputs_dir, ttl_seconds=max(0, int(settings.outputs_ttl_hours)) * 3600)
        yield

    app = FastAPI(title="JetLinks AI API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(meta.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(docs.router, prefix="/api")
    app.include_router(files.router, prefix="/api")
    app.include_router(browser.router, prefix="/api")
    app.include_router(prototype.router, prefix="/api")
    app.include_router(skills.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(team.router, prefix="/api")
    app.include_router(team_integrations.router, prefix="/api")
    app.include_router(wecom.router, prefix="/api")
    app.include_router(feishu.router, prefix="/api")
    app.include_router(history.router, prefix="/api")
    app.include_router(chatbi.router, prefix="/api")
    app.include_router(integrations_openclaw.router, prefix="/api")
    app.include_router(admin_teams.router)
    app.include_router(openai_proxy.router)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    _mount_chatbi(app, settings)
    _mount_ui(app, settings)
    return app


def _mount_chatbi(app: FastAPI, settings: Settings) -> None:
    """
    Optional: mount the bundled ChatBI demo app (ported from stop_project/smart_ask_data).

    This is a standalone sub-app with its own session-based auth and demo data sources.
    It is intentionally isolated from jetlinks-ai's JWT/team auth for now.
    """
    raw = (env_str("ENABLE_CHATBI", "") or "").strip().lower()
    # Disabled by default (JetLinks AI provides a first-class, JWT/team authenticated ChatBI under `/api/chatbi/*`).
    enabled = raw in {"1", "true", "yes", "y", "on"}
    if not enabled:
        return

    vendor_root = (Path(__file__).resolve().parent / "vendor" / "smart_ask_data").resolve()
    if not vendor_root.exists():
        return
    if not (vendor_root / "app" / "main.py").exists():
        return

    try:
        # The vendored app uses absolute imports like `from app...`, so we add its root to sys.path.
        if str(vendor_root) not in sys.path:
            sys.path.insert(0, str(vendor_root))
        from app.main import create_app as create_chatbi_app  # type: ignore[import-not-found]
    except Exception:
        return

    try:
        app.mount("/chatbi", create_chatbi_app())
    except Exception:
        return


def _mount_ui(app: FastAPI, settings: Settings) -> None:
    if _mount_ui_static(app, settings):
        return

    @app.get("/", include_in_schema=False)
    def root() -> HTMLResponse:
        web_port = (env_str("WEB_PORT", "5173") or "5173").strip() or "5173"
        web_url = f"http://127.0.0.1:{web_port}"
        return HTMLResponse(
            f"""
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
	    <title>JetLinks AI</title>
    <style>
      body {{ font-family: -apple-system, system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif; padding: 24px; }}
      code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 6px; }}
    </style>
  </head>
  <body>
		    <h2>JetLinks AI API 已启动</h2>
	    <p>开发模式前端默认在：<a href="{web_url}">{web_url}</a></p>
	    <p>Swagger 文档在：<a href="/docs">/docs</a></p>
	    <p>如果想让后端直接托管前端构建产物：先在 <code>frontend/</code> 运行 <code>pnpm build</code>，或设置 <code>JETLINKS_AI_UI_DIST_DIR</code>。</p>
	  </body>
</html>
""".strip()
        )


def _mount_ui_static(app: FastAPI, settings: Settings) -> bool:
    ui_dist_dir = (env_str("UI_DIST_DIR", "") or "").strip()
    dist = Path(ui_dist_dir).expanduser() if ui_dist_dir else settings.app_root / "frontend" / "dist"
    index = dist / "index.html"
    if not index.exists():
        return False
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")
    return True
