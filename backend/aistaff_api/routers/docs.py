from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pathlib import Path

from pydantic import BaseModel, Field

from ..db import fetchone, row_to_dict
from ..deps import get_current_user, get_db, get_settings
from ..project_utils import resolve_project_path, resolve_user_workspace_root
from ..services.doc_service import DocService
from ..services.workspace_output_service import save_output_to_workspace


async def _resolve_workspace_root(
    *,
    project_id: int | None,
    user,
    settings,
    db,
) -> Path:
    if project_id is not None and int(project_id) > 0:
        proj_row = await fetchone(
            db,
            "SELECT id, team_id, path, enabled FROM team_projects WHERE id = ?",
            (int(project_id),),
        )
        proj = row_to_dict(proj_row) or {}
        if not proj or int(proj.get("team_id") or 0) != int(getattr(user, "team_id", 0)):
            raise HTTPException(status_code=404, detail="项目不存在")
        if not bool(proj.get("enabled")):
            raise HTTPException(status_code=400, detail="项目已禁用")
        try:
            return resolve_project_path(settings, str(proj.get("path") or ""))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"项目路径无效：{e}") from e

    ws_row = await fetchone(db, "SELECT workspace_path FROM team_settings WHERE team_id = ?", (user.team_id,))
    ws = str((row_to_dict(ws_row) or {}).get("workspace_path") or "").strip()
    if ws:
        try:
            base = resolve_project_path(settings, ws)
        except ValueError:
            base = settings.workspace_root
    else:
        base = settings.workspace_root
    try:
        return resolve_user_workspace_root(
            settings,
            Path(base),
            user.team_id,
            user.id,
            user.team_name,
            user.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"用户工作区路径无效：{e}") from e


router = APIRouter(tags=["docs"])


class PptSlide(BaseModel):
    title: str = Field(min_length=1)
    bullets: list[str] = Field(default_factory=list)


class PptRequest(BaseModel):
    title: str = Field(min_length=1)
    slides: list[PptSlide] = Field(min_length=1)
    style: str | None = Field(default=None, description="PPT 风格：auto/modern_blue/minimal_gray/dark_tech/warm_business/template_jetlinks/template_team")
    layout_mode: str | None = Field(default=None, description="版式：auto/focus/single_column/two_column/cards")
    template_file_id: str | None = Field(default=None, description="可选：PPTX 模板文件 file_id（需先上传到 /api/files/upload-file）")
    template_mode: str | None = Field(default=None, description="可选：模板渲染模式（reuse/inplace/preserve）")
    template_keep_images: bool | None = Field(default=None, description="可选：是否保留模板中的非背景图片")
    template_content_indices: list[int] | None = Field(default=None, description="可选：模板内容页索引（1-based，例如 [3,5,7]）")


class QuoteItem(BaseModel):
    name: str = Field(min_length=1)
    # Allow 0 as a placeholder when user doesn't provide quantity yet.
    quantity: float = Field(ge=0)
    unit_price: float = Field(ge=0)
    unit: str = "项"
    note: str | None = None


class QuoteRequest(BaseModel):
    seller: str = Field(min_length=1)
    buyer: str = Field(min_length=1)
    currency: str = "CNY"
    items: list[QuoteItem] = Field(min_length=1)
    note: str | None = None


class InspectionBasicInfo(BaseModel):
    report_no: str | None = None
    report_date: str | None = None
    applicant_unit: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    project_order_no: str | None = None
    inspection_type: str | None = None
    inspection_method: str | None = None
    sampling_standard: str | None = None
    acceptance_standard: str | None = None


class InspectionDeviceInfo(BaseModel):
    device_name: str | None = None
    model: str | None = None
    category: str | None = None
    quantity: str | None = None
    unit: str | None = None
    sn_range: str | None = None
    firmware_version: str | None = None
    hardware_version: str | None = None
    manufacturer: str | None = None
    brand: str | None = None
    batch: str | None = None
    supplier: str | None = None
    doc_no: str | None = None


class InspectionNetworkInfo(BaseModel):
    communication: str | None = None
    carrier_band_power: str | None = None
    sim_iccid: str | None = None
    mac_imei: str | None = None
    security: str | None = None
    key_provisioning: str | None = None
    power: str | None = None
    battery: str | None = None
    certifications: str | None = None
    materials: str | None = None


class InspectionInspectionInfo(BaseModel):
    reference: str | None = None
    environment: str | None = None


class InspectionItem(BaseModel):
    name: str = Field(min_length=1)
    result: str = ""
    remark: str | None = None


class InspectionConclusion(BaseModel):
    result: str | None = None
    defect_level: str | None = None
    disposition: str | None = None
    recheck: str | None = None


class InspectionSignatures(BaseModel):
    reporter: str | None = None
    inspector: str | None = None
    reviewer: str | None = None
    date: str | None = None


class InspectionRequest(BaseModel):
    title: str = Field(default="物联网设备报检单", min_length=1)
    basic_info: InspectionBasicInfo = Field(default_factory=InspectionBasicInfo)
    device_info: InspectionDeviceInfo = Field(default_factory=InspectionDeviceInfo)
    network_info: InspectionNetworkInfo = Field(default_factory=InspectionNetworkInfo)
    inspection_info: InspectionInspectionInfo = Field(default_factory=InspectionInspectionInfo)
    inspection_items: list[InspectionItem] = Field(default_factory=list)
    conclusion: InspectionConclusion = Field(default_factory=InspectionConclusion)
    signatures: InspectionSignatures = Field(default_factory=InspectionSignatures)
    attachments: list[str] = Field(default_factory=list)


@router.post("/docs/ppt")
async def create_ppt(
    req: PptRequest,
    project_id: int | None = Query(default=None),
    user=Depends(get_current_user),  # noqa: ANN001
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    service = DocService(settings)
    try:
        file_meta = await service.create_pptx(
            title=req.title,
            slides=[s.model_dump() for s in req.slides],
            style=req.style,
            layout_mode=req.layout_mode,
            template_file_id=req.template_file_id,
            template_mode=req.template_mode,
            template_keep_images=req.template_keep_images,
            template_content_indices=req.template_content_indices,
        )
        try:
            workspace_root = await _resolve_workspace_root(
                project_id=project_id,
                user=user,
                settings=settings,
                db=db,
            )
            workspace_meta = save_output_to_workspace(
                settings=settings,
                workspace_root=workspace_root,
                file_id=str(file_meta.get("file_id") or ""),
                title=req.title,
                kind="pptx",
                payload=req.model_dump(),
                meta=file_meta,
                source="/api/docs/ppt",
            )
            file_meta.update(workspace_meta)
        except Exception:
            pass
        return file_meta
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/docs/quote")
async def create_quote(
    req: QuoteRequest,
    project_id: int | None = Query(default=None),
    user=Depends(get_current_user),  # noqa: ANN001
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    service = DocService(settings)
    try:
        file_meta = await service.create_quote_docx(
            seller=req.seller,
            buyer=req.buyer,
            currency=req.currency,
            items=[i.model_dump() for i in req.items],
            note=req.note,
        )
        try:
            workspace_root = await _resolve_workspace_root(
                project_id=project_id,
                user=user,
                settings=settings,
                db=db,
            )
            workspace_meta = save_output_to_workspace(
                settings=settings,
                workspace_root=workspace_root,
                file_id=str(file_meta.get("file_id") or ""),
                title="报价单",
                kind="docx",
                payload=req.model_dump(),
                meta=file_meta,
                source="/api/docs/quote",
            )
            file_meta.update(workspace_meta)
        except Exception:
            pass
        return file_meta
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/docs/quote-xlsx")
async def create_quote_xlsx(
    req: QuoteRequest,
    project_id: int | None = Query(default=None),
    user=Depends(get_current_user),  # noqa: ANN001
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    service = DocService(settings)
    try:
        file_meta = await service.create_quote_xlsx(
            seller=req.seller,
            buyer=req.buyer,
            currency=req.currency,
            items=[i.model_dump() for i in req.items],
            note=req.note,
        )
        try:
            workspace_root = await _resolve_workspace_root(
                project_id=project_id,
                user=user,
                settings=settings,
                db=db,
            )
            workspace_meta = save_output_to_workspace(
                settings=settings,
                workspace_root=workspace_root,
                file_id=str(file_meta.get("file_id") or ""),
                title="报价单",
                kind="xlsx",
                payload=req.model_dump(),
                meta=file_meta,
                source="/api/docs/quote-xlsx",
            )
            file_meta.update(workspace_meta)
        except Exception:
            pass
        return file_meta
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/docs/inspection")
async def create_inspection(
    req: InspectionRequest,
    project_id: int | None = Query(default=None),
    user=Depends(get_current_user),  # noqa: ANN001
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    service = DocService(settings)
    try:
        file_meta = await service.create_inspection_docx(
            title=req.title,
            basic_info=req.basic_info.model_dump(),
            device_info=req.device_info.model_dump(),
            network_info=req.network_info.model_dump(),
            inspection_info=req.inspection_info.model_dump(),
            inspection_items=[i.model_dump() for i in req.inspection_items],
            conclusion=req.conclusion.model_dump(),
            signatures=req.signatures.model_dump(),
            attachments=req.attachments or None,
        )
        try:
            workspace_root = await _resolve_workspace_root(
                project_id=project_id,
                user=user,
                settings=settings,
                db=db,
            )
            workspace_meta = save_output_to_workspace(
                settings=settings,
                workspace_root=workspace_root,
                file_id=str(file_meta.get("file_id") or ""),
                title=req.title,
                kind="docx",
                payload=req.model_dump(),
                meta=file_meta,
                source="/api/docs/inspection",
            )
            file_meta.update(workspace_meta)
        except Exception:
            pass
        return file_meta
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/docs/inspection-xlsx")
async def create_inspection_xlsx(
    req: InspectionRequest,
    project_id: int | None = Query(default=None),
    user=Depends(get_current_user),  # noqa: ANN001
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    service = DocService(settings)
    try:
        file_meta = await service.create_inspection_xlsx(
            title=req.title,
            basic_info=req.basic_info.model_dump(),
            device_info=req.device_info.model_dump(),
            network_info=req.network_info.model_dump(),
            inspection_info=req.inspection_info.model_dump(),
            inspection_items=[i.model_dump() for i in req.inspection_items],
            conclusion=req.conclusion.model_dump(),
            signatures=req.signatures.model_dump(),
            attachments=req.attachments or None,
        )
        try:
            workspace_root = await _resolve_workspace_root(
                project_id=project_id,
                user=user,
                settings=settings,
                db=db,
            )
            workspace_meta = save_output_to_workspace(
                settings=settings,
                workspace_root=workspace_root,
                file_id=str(file_meta.get("file_id") or ""),
                title=req.title,
                kind="xlsx",
                payload=req.model_dump(),
                meta=file_meta,
                source="/api/docs/inspection-xlsx",
            )
            file_meta.update(workspace_meta)
        except Exception:
            pass
        return file_meta
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
