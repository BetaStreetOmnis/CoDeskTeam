from __future__ import annotations

from pydantic import BaseModel, Field

from .base import ToolContext, ToolDefinition
from ...services.doc_service import DocService
from ...services.workspace_output_service import save_output_to_workspace
from ...config import load_settings


class PptSlide(BaseModel):
    title: str = Field(min_length=1)
    bullets: list[str] = Field(default_factory=list)


class DocPptxCreateArgs(BaseModel):
    title: str = Field(min_length=1)
    slides: list[PptSlide] = Field(min_length=1)
    style: str | None = None
    layout_mode: str | None = None
    template_file_id: str | None = None
    template_mode: str | None = None
    template_keep_images: bool | None = None
    template_content_indices: list[int] | None = None


class QuoteItem(BaseModel):
    name: str = Field(min_length=1)
    # Allow 0 as a placeholder when user doesn't provide quantity yet.
    quantity: float = Field(ge=0)
    unit_price: float = Field(ge=0)
    unit: str = "项"
    note: str | None = None


class DocQuoteCreateArgs(BaseModel):
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


def _default_inspection_items() -> list[InspectionItem]:
    names = [
        "外观与包装",
        "标识与追溯（铭牌/SN/二维码）",
        "通电自检/启动",
        "传感/采集精度（如适用）",
        "通信注册/入网/连接稳定性",
        "平台对接（MQTT/HTTP/CoAP 等）",
        "远程配置/OTA 升级",
        "告警/事件上报",
        "功耗/续航（如适用）",
        "安全项（TLS/证书/密钥/弱口令）",
        "其他",
    ]
    return [InspectionItem(name=n) for n in names]


class DocInspectionCreateArgs(BaseModel):
    title: str = Field(default="物联网设备报检单", min_length=1)
    basic_info: InspectionBasicInfo = Field(default_factory=InspectionBasicInfo)
    device_info: InspectionDeviceInfo = Field(default_factory=InspectionDeviceInfo)
    network_info: InspectionNetworkInfo = Field(default_factory=InspectionNetworkInfo)
    inspection_info: InspectionInspectionInfo = Field(default_factory=InspectionInspectionInfo)
    inspection_items: list[InspectionItem] = Field(default_factory=_default_inspection_items)
    conclusion: InspectionConclusion = Field(default_factory=InspectionConclusion)
    signatures: InspectionSignatures = Field(default_factory=InspectionSignatures)
    attachments: list[str] = Field(default_factory=list)


def doc_pptx_create_tool() -> ToolDefinition:
    async def handler(args: DocPptxCreateArgs, ctx: ToolContext) -> dict:
        settings = load_settings()
        service = DocService(settings)
        meta = await service.create_pptx(
            title=args.title,
            slides=[s.model_dump() for s in args.slides],
            style=args.style,
            layout_mode=args.layout_mode,
            template_file_id=args.template_file_id,
            template_mode=args.template_mode,
            template_keep_images=args.template_keep_images,
            template_content_indices=args.template_content_indices,
        )
        try:
            workspace_meta = save_output_to_workspace(
                settings=settings,
                workspace_root=ctx.workspace_root,
                file_id=str(meta.get("file_id") or ""),
                title=args.title,
                kind="pptx",
                payload=args.model_dump(),
                meta=meta,
                source="tool:doc_pptx_create",
            )
            meta.update(workspace_meta)
        except Exception:
            pass
        return meta

    return ToolDefinition(
        name="doc_pptx_create",
        description="生成 PPTX（支持多风格 style 与版式 layout_mode；也支持指定 template_file_id 复用自定义 PPT 模板，写入输出目录并返回下载链接）",
        risk="safe",
        input_model=DocPptxCreateArgs,
        handler=handler,
        parameters_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "slides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "title": {"type": "string"},
                            "bullets": {"type": "array", "items": {"type": "string"}, "default": []},
                        },
                        "required": ["title"],
                    },
                },
                "style": {
                    "type": "string",
                    "enum": [
                        "auto",
                        "modern_blue",
                        "minimal_gray",
                        "dark_tech",
                        "warm_business",
                        "template_jetlinks",
                        "template_team",
                    ],
                    "default": "auto",
                },
                "layout_mode": {
                    "type": "string",
                    "enum": ["auto", "focus", "single_column", "two_column", "cards"],
                    "default": "auto",
                },
                "template_file_id": {"type": "string", "default": None, "description": "可选：上传的 PPTX 模板 file_id"},
                "template_mode": {"type": "string", "default": None, "description": "可选：模板渲染模式（reuse/inplace/preserve）"},
                "template_keep_images": {"type": "boolean", "default": None, "description": "可选：是否保留模板非背景图片"},
                "template_content_indices": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "default": None,
                    "description": "可选：模板内容页索引（1-based）",
                },
            },
            "required": ["title", "slides"],
        },
    )


def doc_quote_docx_create_tool() -> ToolDefinition:
    async def handler(args: DocQuoteCreateArgs, ctx: ToolContext) -> dict:
        settings = load_settings()
        service = DocService(settings)
        meta = await service.create_quote_docx(
            seller=args.seller,
            buyer=args.buyer,
            currency=args.currency,
            items=[i.model_dump() for i in args.items],
            note=args.note,
        )
        try:
            workspace_meta = save_output_to_workspace(
                settings=settings,
                workspace_root=ctx.workspace_root,
                file_id=str(meta.get("file_id") or ""),
                title="报价单",
                kind="docx",
                payload=args.model_dump(),
                meta=meta,
                source="tool:doc_quote_docx_create",
            )
            meta.update(workspace_meta)
        except Exception:
            pass
        return meta

    return ToolDefinition(
        name="doc_quote_docx_create",
        description="生成报价单 DOCX（写入输出目录并返回下载链接）",
        risk="safe",
        input_model=DocQuoteCreateArgs,
        handler=handler,
        parameters_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "seller": {"type": "string"},
                "buyer": {"type": "string"},
                "currency": {"type": "string", "default": "CNY"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "quantity": {"type": "number"},
                            "unit_price": {"type": "number"},
                            "unit": {"type": "string", "default": "项"},
                        },
                        "required": ["name", "quantity", "unit_price"],
                    },
                },
                "note": {"type": "string"},
            },
            "required": ["seller", "buyer", "items"],
        },
    )


def doc_quote_xlsx_create_tool() -> ToolDefinition:
    async def handler(args: DocQuoteCreateArgs, ctx: ToolContext) -> dict:
        settings = load_settings()
        service = DocService(settings)
        meta = await service.create_quote_xlsx(
            seller=args.seller,
            buyer=args.buyer,
            currency=args.currency,
            items=[i.model_dump() for i in args.items],
            note=args.note,
        )
        try:
            workspace_meta = save_output_to_workspace(
                settings=settings,
                workspace_root=ctx.workspace_root,
                file_id=str(meta.get("file_id") or ""),
                title="报价单",
                kind="xlsx",
                payload=args.model_dump(),
                meta=meta,
                source="tool:doc_quote_xlsx_create",
            )
            meta.update(workspace_meta)
        except Exception:
            pass
        return meta

    return ToolDefinition(
        name="doc_quote_xlsx_create",
        description="生成报价单 XLSX（专业样式，写入输出目录并返回下载链接）",
        risk="safe",
        input_model=DocQuoteCreateArgs,
        handler=handler,
        parameters_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "seller": {"type": "string"},
                "buyer": {"type": "string"},
                "currency": {"type": "string", "default": "CNY"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "quantity": {"type": "number"},
                            "unit_price": {"type": "number"},
                            "unit": {"type": "string", "default": "项"},
                            "note": {"type": "string"},
                        },
                        "required": ["name", "quantity", "unit_price"],
                    },
                },
                "note": {"type": "string"},
            },
            "required": ["seller", "buyer", "items"],
        },
    )


def doc_inspection_docx_create_tool() -> ToolDefinition:
    async def handler(args: DocInspectionCreateArgs, ctx: ToolContext) -> dict:
        settings = load_settings()
        service = DocService(settings)
        meta = await service.create_inspection_docx(
            title=args.title,
            basic_info=args.basic_info.model_dump(),
            device_info=args.device_info.model_dump(),
            network_info=args.network_info.model_dump(),
            inspection_info=args.inspection_info.model_dump(),
            inspection_items=[i.model_dump() for i in args.inspection_items],
            conclusion=args.conclusion.model_dump(),
            signatures=args.signatures.model_dump(),
            attachments=args.attachments or None,
        )
        try:
            workspace_meta = save_output_to_workspace(
                settings=settings,
                workspace_root=ctx.workspace_root,
                file_id=str(meta.get("file_id") or ""),
                title=args.title,
                kind="docx",
                payload=args.model_dump(),
                meta=meta,
                source="tool:doc_inspection_docx_create",
            )
            meta.update(workspace_meta)
        except Exception:
            pass
        return meta

    return ToolDefinition(
        name="doc_inspection_docx_create",
        description="生成报检单/检验单 DOCX（写入输出目录并返回下载链接）",
        risk="safe",
        input_model=DocInspectionCreateArgs,
        handler=handler,
        parameters_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string", "default": "物联网设备报检单"},
                "basic_info": {"type": "object"},
                "device_info": {"type": "object"},
                "network_info": {"type": "object"},
                "inspection_info": {"type": "object"},
                "inspection_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "result": {"type": "string", "default": ""},
                            "remark": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                },
                "conclusion": {"type": "object"},
                "signatures": {"type": "object"},
                "attachments": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            "required": ["title"],
        },
    )


def doc_inspection_xlsx_create_tool() -> ToolDefinition:
    async def handler(args: DocInspectionCreateArgs, ctx: ToolContext) -> dict:
        settings = load_settings()
        service = DocService(settings)
        meta = await service.create_inspection_xlsx(
            title=args.title,
            basic_info=args.basic_info.model_dump(),
            device_info=args.device_info.model_dump(),
            network_info=args.network_info.model_dump(),
            inspection_info=args.inspection_info.model_dump(),
            inspection_items=[i.model_dump() for i in args.inspection_items],
            conclusion=args.conclusion.model_dump(),
            signatures=args.signatures.model_dump(),
            attachments=args.attachments or None,
        )
        try:
            workspace_meta = save_output_to_workspace(
                settings=settings,
                workspace_root=ctx.workspace_root,
                file_id=str(meta.get("file_id") or ""),
                title=args.title,
                kind="xlsx",
                payload=args.model_dump(),
                meta=meta,
                source="tool:doc_inspection_xlsx_create",
            )
            meta.update(workspace_meta)
        except Exception:
            pass
        return meta

    return ToolDefinition(
        name="doc_inspection_xlsx_create",
        description="生成报检单/检验单 XLSX（写入输出目录并返回下载链接）",
        risk="safe",
        input_model=DocInspectionCreateArgs,
        handler=handler,
        parameters_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string", "default": "物联网设备报检单"},
                "basic_info": {"type": "object"},
                "device_info": {"type": "object"},
                "network_info": {"type": "object"},
                "inspection_info": {"type": "object"},
                "inspection_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "result": {"type": "string", "default": ""},
                            "remark": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                },
                "conclusion": {"type": "object"},
                "signatures": {"type": "object"},
                "attachments": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            "required": ["title"],
        },
    )
