from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

from .base import ToolContext, ToolDefinition


_SENSITIVE_ENV_FILENAMES = {".env.example", ".env.sample", ".env.template"}


def _is_sensitive_resolved_path(workspace_root: Path, resolved: Path) -> bool:
    try:
        rel = resolved.relative_to(workspace_root.resolve())
    except Exception:
        return True

    parts = {p.lower() for p in rel.parts}
    if ".aistaff" in parts:
        return True

    name = resolved.name.lower()
    if name in _SENSITIVE_ENV_FILENAMES:
        return False
    if name == ".env" or name.startswith(".env."):
        return True

    return False


def _resolve_in_workspace(workspace_root: Path, input_path: str) -> Path:
    root = workspace_root.resolve()
    resolved = (root / input_path).resolve()
    if resolved == root or str(resolved).startswith(str(root) + os.sep):
        if _is_sensitive_resolved_path(root, resolved):
            raise ValueError(f"Access denied for sensitive path: {input_path}")
        return resolved
    raise ValueError(f"Path escapes workspace root: {input_path}")


class FsReadArgs(BaseModel):
    path: str = Field(min_length=1)


class FsListArgs(BaseModel):
    path: str = "."
    depth: int = Field(default=2, ge=0, le=6)
    max_entries: int = Field(default=500, ge=1, le=5000)


class FsWriteArgs(BaseModel):
    path: str = Field(min_length=1)
    content: str
    mode: str = Field(default="overwrite", pattern="^(overwrite|append)$")


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 14)] + "\n…(truncated)"


def _list_dir_recursive(base: Path, *, depth: int, max_entries: int, prefix: str = "") -> list[str]:
    if max_entries <= 0:
        return []
    if not base.exists():
        return []
    lines: list[str] = []
    try:
        entries = sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except Exception:
        return []

    for p in entries:
        if len(lines) >= max_entries:
            break
        marker = "/" if p.is_dir() else ""
        lines.append(f"{prefix}{p.name}{marker}")
        if p.is_dir() and depth > 0:
            lines.extend(_list_dir_recursive(p, depth=depth - 1, max_entries=max_entries - len(lines), prefix=f"{prefix}{p.name}/"))
    return lines


def fs_list_tool() -> ToolDefinition:
    async def handler(args: FsListArgs, ctx: ToolContext) -> str:
        full = _resolve_in_workspace(ctx.workspace_root, args.path)
        lines = _list_dir_recursive(full, depth=args.depth, max_entries=args.max_entries)
        return "\n".join(lines)

    return ToolDefinition(
        name="fs_list",
        description="列出工作区目录树（用于了解文件结构）",
        risk="safe",
        input_model=FsListArgs,
        handler=handler,
        parameters_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "path": {"type": "string", "default": "."},
                "depth": {"type": "integer", "minimum": 0, "maximum": 6, "default": 2},
                "max_entries": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 500},
            },
        },
    )


def fs_read_tool() -> ToolDefinition:
    async def handler(args: FsReadArgs, ctx: ToolContext) -> str:
        full = _resolve_in_workspace(ctx.workspace_root, args.path)
        content = full.read_text(encoding="utf-8")
        return _truncate(content, ctx.max_file_read_chars)

    return ToolDefinition(
        name="fs_read",
        description="读取工作区内的文本文件",
        risk="safe",
        input_model=FsReadArgs,
        handler=handler,
        parameters_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )


def fs_write_tool() -> ToolDefinition:
    async def handler(args: FsWriteArgs, ctx: ToolContext) -> dict:
        if not ctx.enable_write:
            raise ValueError("fs_write is disabled (AISTAFF_ENABLE_WRITE=1).")
        full = _resolve_in_workspace(ctx.workspace_root, args.path)
        full.parent.mkdir(parents=True, exist_ok=True)
        if args.mode == "append":
            full.write_text((full.read_text(encoding="utf-8") if full.exists() else "") + args.content, encoding="utf-8")
        else:
            full.write_text(args.content, encoding="utf-8")
        return {"ok": True, "path": args.path, "mode": args.mode}

    return ToolDefinition(
        name="fs_write",
        description="写入工作区内的文本文件（默认禁用，需要显式开启）",
        risk="dangerous",
        input_model=FsWriteArgs,
        handler=handler,
        parameters_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "mode": {"type": "string", "enum": ["overwrite", "append"], "default": "overwrite"},
            },
            "required": ["path", "content"],
        },
    )
