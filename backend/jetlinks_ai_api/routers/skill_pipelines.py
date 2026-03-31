from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ..deps import get_current_user, get_db, get_settings
from ..services.toolkit_pipeline_service import ToolkitPipelineService


router = APIRouter(tags=["skill-pipelines"])


class ToolkitPipelineRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    deployment_mode: str = "hybrid"
    operation: str = "auto"
    prompt: str | None = None
    input_file_ids: list[str] = Field(default_factory=list)
    target_formats: list[str] = Field(default_factory=lambda: ["webp", "jpg", "png"])
    resize: dict[str, Any] = Field(default_factory=dict)
    enhance: bool = True
    size: str = "1024x1024"
    quality: str = "auto"
    background: str = "auto"
    output_format: str = "png"
    input_fidelity: str = "high"
    clip_seconds: int = 15
    topic: str | None = None
    audience: str | None = None
    tone: str | None = None
    key_points: list[str] = Field(default_factory=list)
    project_name: str | None = None
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    pipelines: list[str] = Field(default_factory=list)
    vision_payload: dict[str, Any] = Field(default_factory=dict)
    media_payload: dict[str, Any] = Field(default_factory=dict)
    content_payload: dict[str, Any] = Field(default_factory=dict)
    office_payload: dict[str, Any] = Field(default_factory=dict)


async def _run(
    *,
    pipeline_id: str,
    req: ToolkitPipelineRequest,
    project_id: int | None,
    user,
    settings,
    db,
) -> dict:
    service = ToolkitPipelineService(settings)
    try:
        return await service.run_pipeline(
            pipeline_id=pipeline_id,
            payload=req.model_dump(),
            user=user,
            db=db,
            project_id=project_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/skills/pipeline/vision")
async def run_vision_pipeline(
    req: ToolkitPipelineRequest,
    project_id: int | None = Query(default=None),
    user=Depends(get_current_user),  # noqa: ANN001
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    return await _run(
        pipeline_id="vision",
        req=req,
        project_id=project_id,
        user=user,
        settings=settings,
        db=db,
    )


@router.post("/skills/pipeline/media")
async def run_media_pipeline(
    req: ToolkitPipelineRequest,
    project_id: int | None = Query(default=None),
    user=Depends(get_current_user),  # noqa: ANN001
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    return await _run(
        pipeline_id="media",
        req=req,
        project_id=project_id,
        user=user,
        settings=settings,
        db=db,
    )


@router.post("/skills/pipeline/content")
async def run_content_pipeline(
    req: ToolkitPipelineRequest,
    project_id: int | None = Query(default=None),
    user=Depends(get_current_user),  # noqa: ANN001
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    return await _run(
        pipeline_id="content",
        req=req,
        project_id=project_id,
        user=user,
        settings=settings,
        db=db,
    )


@router.post("/skills/pipeline/office")
async def run_office_pipeline(
    req: ToolkitPipelineRequest,
    project_id: int | None = Query(default=None),
    user=Depends(get_current_user),  # noqa: ANN001
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    return await _run(
        pipeline_id="office",
        req=req,
        project_id=project_id,
        user=user,
        settings=settings,
        db=db,
    )


@router.post("/skills/pipeline/full")
async def run_full_pipeline(
    req: ToolkitPipelineRequest,
    project_id: int | None = Query(default=None),
    user=Depends(get_current_user),  # noqa: ANN001
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    return await _run(
        pipeline_id="full",
        req=req,
        project_id=project_id,
        user=user,
        settings=settings,
        db=db,
    )
