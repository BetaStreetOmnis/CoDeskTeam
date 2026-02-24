from __future__ import annotations

from pydantic import BaseModel, Field

from .base import ToolContext, ToolDefinition
from ...config import load_settings
from ...services.browser_service import BrowserService


class BrowserNavigateArgs(BaseModel):
    url: str = Field(min_length=1)


def browser_start_tool() -> ToolDefinition:
    async def handler(args: BaseModel, ctx: ToolContext) -> dict:
        _ = args
        if not ctx.session_id:
            raise ValueError("Missing session_id in tool context")
        settings = load_settings()
        service = BrowserService(settings)
        await service.start(ctx.session_id)
        return {"ok": True}

    class EmptyArgs(BaseModel):
        pass

    return ToolDefinition(
        name="browser_start",
        description="启动浏览器会话（Playwright）",
        risk="dangerous",
        input_model=EmptyArgs,
        handler=handler,
        parameters_schema={"type": "object", "additionalProperties": False, "properties": {}},
    )


def browser_navigate_tool() -> ToolDefinition:
    async def handler(args: BrowserNavigateArgs, ctx: ToolContext) -> dict:
        if not ctx.session_id:
            raise ValueError("Missing session_id in tool context")
        settings = load_settings()
        service = BrowserService(settings)
        await service.navigate(ctx.session_id, args.url)
        return {"ok": True, "url": args.url}

    return ToolDefinition(
        name="browser_navigate",
        description="浏览器跳转到指定 URL（Playwright）",
        risk="dangerous",
        input_model=BrowserNavigateArgs,
        handler=handler,
        parameters_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    )


def browser_screenshot_tool() -> ToolDefinition:
    async def handler(args: BaseModel, ctx: ToolContext) -> dict:
        _ = args
        if not ctx.session_id:
            raise ValueError("Missing session_id in tool context")
        settings = load_settings()
        service = BrowserService(settings)
        meta = await service.screenshot_file(ctx.session_id)
        return meta

    class EmptyArgs(BaseModel):
        pass

    return ToolDefinition(
        name="browser_screenshot",
        description="对当前页面截图并返回下载链接（Playwright）",
        risk="dangerous",
        input_model=EmptyArgs,
        handler=handler,
        parameters_schema={"type": "object", "additionalProperties": False, "properties": {}},
    )

