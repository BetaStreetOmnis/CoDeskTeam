from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import get_current_user, get_settings
from ..services.browser_service import BrowserService
from ..session_store import get_session_store


router = APIRouter(tags=["browser"])


class BrowserStartRequest(BaseModel):
    session_id: str = Field(min_length=1)


class BrowserNavigateRequest(BaseModel):
    session_id: str = Field(min_length=1)
    url: str = Field(min_length=1)


class BrowserScreenshotRequest(BaseModel):
    session_id: str = Field(min_length=1)


async def _assert_session_access(*, session_id: str, user, settings) -> None:  # noqa: ANN001
    if getattr(user, "team_role", "") not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="需要团队管理员权限")

    store = get_session_store()
    try:
        await store.assert_access(
            session_id=session_id,
            user_id=user.id,
            team_id=user.team_id,
            ttl_seconds=max(0, int(settings.session_ttl_minutes)) * 60,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="会话不存在或已过期，请先发起对话") from None


@router.post("/browser/start")
async def browser_start(req: BrowserStartRequest, user=Depends(get_current_user), settings=Depends(get_settings)) -> dict:  # noqa: ANN001
    service = BrowserService(settings)
    try:
        await _assert_session_access(session_id=req.session_id, user=user, settings=settings)
        await service.start(req.session_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/browser/navigate")
async def browser_navigate(req: BrowserNavigateRequest, user=Depends(get_current_user), settings=Depends(get_settings)) -> dict:  # noqa: ANN001
    service = BrowserService(settings)
    try:
        await _assert_session_access(session_id=req.session_id, user=user, settings=settings)
        await service.navigate(req.session_id, req.url)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/browser/screenshot")
async def browser_screenshot(req: BrowserScreenshotRequest, user=Depends(get_current_user), settings=Depends(get_settings)) -> dict:  # noqa: ANN001
    service = BrowserService(settings)
    try:
        await _assert_session_access(session_id=req.session_id, user=user, settings=settings)
        img_b64 = await service.screenshot_base64(req.session_id)
        return {"ok": True, "image_base64": img_b64}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
