from __future__ import annotations

from pydantic import BaseModel, Field

from .base import ToolContext, ToolDefinition
from ...config import load_settings
from ...services.prototype_service import PrototypeService
from ...services.workspace_output_service import save_output_to_workspace


class PrototypePage(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    slug: str | None = None


class PrototypeGenerateArgs(BaseModel):
    project_name: str = Field(min_length=1)
    pages: list[PrototypePage] = Field(min_length=1)


def proto_generate_tool() -> ToolDefinition:
    async def handler(args: PrototypeGenerateArgs, ctx: ToolContext) -> dict:
        settings = load_settings()
        service = PrototypeService(settings)
        meta = await service.generate(project_name=args.project_name, pages=[p.model_dump() for p in args.pages])
        try:
            workspace_meta = save_output_to_workspace(
                settings=settings,
                workspace_root=ctx.workspace_root,
                file_id=str(meta.get("file_id") or ""),
                title=args.project_name,
                kind="prototype_zip",
                payload=args.model_dump(),
                meta=meta,
                source="tool:proto_generate",
            )
            meta.update(workspace_meta)
        except Exception:
            pass
        return meta

    return ToolDefinition(
        name="proto_generate",
        description="生成原型 HTML 打包（ZIP），风格参考既有脚本页面",
        risk="safe",
        input_model=PrototypeGenerateArgs,
        handler=handler,
        parameters_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "project_name": {"type": "string"},
                "pages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "slug": {"type": "string"},
                        },
                        "required": ["title"],
                    },
                },
            },
            "required": ["project_name", "pages"],
        },
    )
