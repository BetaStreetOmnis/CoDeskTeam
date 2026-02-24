from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.settings import get_settings
from app.routers.api import router as api_router
from app.routers.data_dev import router as data_dev_router
from app.routers.pages import router as pages_router
from app.services.demo_db import ensure_demo_db


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        https_only=settings.session_https_only,
        same_site=settings.session_same_site,
    )

    root_dir = Path(__file__).resolve().parents[1]
    static_dir = root_dir / "static"
    templates_dir = root_dir / "templates"
    storage_dir = root_dir / "storage"

    static_dir.mkdir(parents=True, exist_ok=True)
    templates_dir.mkdir(parents=True, exist_ok=True)
    storage_dir.mkdir(parents=True, exist_ok=True)

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(pages_router)
    app.include_router(api_router, prefix="/api")
    app.include_router(data_dev_router, prefix="/api/dev")

    @app.on_event("startup")
    def _startup() -> None:
        ensure_demo_db(settings.demo_db_path)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "app": settings.app_name, "version": settings.app_version}

    return app


app = create_app()
