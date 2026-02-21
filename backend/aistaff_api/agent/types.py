from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments_json: str


ChatRole = Literal["system", "user", "assistant", "tool"]


@dataclass
class ChatMessage:
    role: ChatRole
    content: str | None = None
    attachments: list[dict[str, Any]] | None = None
    # tool message
    tool_call_id: str | None = None
    name: str | None = None
    # assistant tool calls (OpenAI format)
    tool_calls: list[dict[str, Any]] | None = None

    def to_openai(self) -> dict[str, Any]:
        if self.role == "tool":
            return {"role": "tool", "tool_call_id": self.tool_call_id, "content": self.content or ""}
        if self.role == "assistant":
            payload: dict[str, Any] = {"role": "assistant", "content": self.content}
            if self.tool_calls:
                payload["tool_calls"] = self.tool_calls
            return payload
        return {"role": self.role, "content": self.content or ""}


@dataclass
class AgentEvent:
    type: str
    data: dict[str, Any]
