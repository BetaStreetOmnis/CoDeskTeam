from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from .base import ToolContext, ToolDefinition


class ShellRunArgs(BaseModel):
    command: str = Field(min_length=1)
    timeout_ms: int = Field(default=60_000, ge=0, le=10 * 60_000)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 14)] + "\n…(truncated)"


def shell_run_tool() -> ToolDefinition:
    async def handler(args: ShellRunArgs, ctx: ToolContext) -> dict:
        if not ctx.enable_shell:
            raise ValueError("shell_run is disabled (AISTAFF_ENABLE_SHELL=1).")

        proc = await asyncio.create_subprocess_shell(
            args.command,
            cwd=str(ctx.workspace_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        timed_out = False
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=args.timeout_ms / 1000 if args.timeout_ms else None)
        except asyncio.TimeoutError:
            timed_out = True
            proc.kill()
            stdout_b, stderr_b = await proc.communicate()

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        combined = stdout + stderr
        if len(combined) > ctx.max_tool_output_chars:
            stdout = _truncate(stdout, ctx.max_tool_output_chars // 2)
            stderr = _truncate(stderr, ctx.max_tool_output_chars // 2)

        return {"exit_code": proc.returncode, "stdout": stdout, "stderr": stderr, "timed_out": timed_out}

    return ToolDefinition(
        name="shell_run",
        description="在工作区根目录执行 shell 命令（默认禁用，需要显式开启）",
        risk="dangerous",
        input_model=ShellRunArgs,
        handler=handler,
        parameters_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "command": {"type": "string"},
                "timeout_ms": {"type": "integer", "minimum": 0, "maximum": 600000, "default": 60000},
            },
            "required": ["command"],
        },
    )
