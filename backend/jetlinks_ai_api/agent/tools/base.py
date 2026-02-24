from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, Type

from pydantic import BaseModel


ToolRisk = Literal["safe", "dangerous"]


@dataclass(frozen=True)
class ToolContext:
    session_id: str | None
    workspace_root: Path
    outputs_dir: Path
    enable_shell: bool
    enable_write: bool
    enable_browser: bool
    max_file_read_chars: int
    max_tool_output_chars: int
    max_context_chars: int


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    risk: ToolRisk
    input_model: Type[BaseModel]
    handler: Callable[[BaseModel, ToolContext], Awaitable[Any]]
    parameters_schema: dict[str, Any]
