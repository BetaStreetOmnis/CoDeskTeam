from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..types import ChatMessage, ToolCall
from ..tools.base import ToolDefinition


@dataclass(frozen=True)
class ModelResponse:
    assistant_text: str | None
    tool_calls: list[ToolCall]


class ModelProvider(Protocol):
    name: str

    async def complete(self, *, model: str, messages: list[ChatMessage], tools: list[ToolDefinition]) -> ModelResponse: ...

