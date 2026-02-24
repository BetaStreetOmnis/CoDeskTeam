from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/data-dev", response_class=HTMLResponse)
def data_dev(request: Request):
    return templates.TemplateResponse("data_dev.html", {"request": request})


@router.get("/datasources", response_class=HTMLResponse)
def datasources(request: Request):
    return templates.TemplateResponse("datasources.html", {"request": request})
