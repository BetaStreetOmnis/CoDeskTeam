from __future__ import annotations

import json
from typing import Any, Callable, Awaitable

from .types import AgentEvent, ChatMessage
from .providers.base import ModelProvider
from .tools.base import ToolContext, ToolDefinition


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 14)] + "\n…(truncated)"


def _estimate_chars(m: ChatMessage) -> int:
    n = len(m.content or "")
    if m.attachments:
        try:
            n += sum(len(str(a.get("file_id") or "")) + len(str(a.get("filename") or "")) for a in m.attachments if isinstance(a, dict))
        except Exception:
            pass
    if m.tool_calls:
        try:
            n += len(json.dumps(m.tool_calls, ensure_ascii=False))
        except Exception:
            n += len(str(m.tool_calls))
    # Rough overhead per message (role labels, separators).
    return n + 64


def _trim_for_context(messages: list[ChatMessage], max_chars: int) -> tuple[list[ChatMessage], int]:
    if max_chars <= 0:
        return messages, 0

    system_msgs: list[ChatMessage] = [m for m in messages if m.role == "system"]
    rest: list[ChatMessage] = [m for m in messages if m.role != "system"]
    kept: list[ChatMessage] = []
    total = 0
    for m in reversed(rest):
        est = _estimate_chars(m)
        if kept and (total + est) > max_chars:
            break
        kept.append(m)
        total += est
    kept.reverse()
    dropped = max(0, len(rest) - len(kept))
    return [*system_msgs, *kept], dropped


async def run_agent_task(
    *,
    provider: ModelProvider,
    model: str,
    messages: list[ChatMessage],
    user_input: str,
    user_attachments: list[dict[str, Any]] | None,
    tools: list[ToolDefinition],
    tool_ctx: ToolContext,
    max_steps: int,
    on_event: Callable[[AgentEvent], Awaitable[None]] | None = None,
) -> tuple[str, list[ChatMessage]]:
    messages = [*messages, ChatMessage(role="user", content=user_input, attachments=user_attachments or None)]
    tool_by_name = {t.name: t for t in tools}

    async def emit(event_type: str, data: dict[str, Any]) -> None:
        if on_event:
            await on_event(AgentEvent(type=event_type, data=data))

    for _step in range(max_steps):
        if tool_ctx.max_context_chars > 0:
            messages, dropped = _trim_for_context(messages, max_chars=int(tool_ctx.max_context_chars))
            if dropped:
                await emit("context_trim", {"dropped": dropped, "max_chars": int(tool_ctx.max_context_chars)})
        response = await provider.complete(model=model, messages=messages, tools=tools)

        if response.tool_calls:
            # record assistant tool call message (OpenAI format)
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.assistant_text,
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments_json},
                        }
                        for tc in response.tool_calls
                    ],
                )
            )

            for tc in response.tool_calls:
                tool = tool_by_name.get(tc.name)
                if not tool:
                    await emit("error", {"message": f"Unknown tool: {tc.name}"})
                    messages.append(ChatMessage(role="tool", tool_call_id=tc.id, content=f"Unknown tool: {tc.name}"))
                    continue

                try:
                    raw_args = json.loads(tc.arguments_json or "{}")
                except Exception as e:
                    await emit("error", {"message": f"Invalid JSON for tool {tc.name}: {e}"})
                    messages.append(ChatMessage(role="tool", tool_call_id=tc.id, content=f"Invalid JSON: {e}"))
                    continue

                await emit("tool_call", {"tool": tc.name, "args": raw_args})

                try:
                    parsed = tool.input_model.model_validate(raw_args)
                    result = await tool.handler(parsed, tool_ctx)
                    await emit("tool_result", {"tool": tc.name, "result": result})

                    content = _truncate(json.dumps(result, ensure_ascii=False, indent=2), tool_ctx.max_tool_output_chars)
                    messages.append(ChatMessage(role="tool", tool_call_id=tc.id, content=content))
                except Exception as e:
                    await emit("error", {"message": f"Tool {tc.name} failed: {e}"})
                    messages.append(ChatMessage(role="tool", tool_call_id=tc.id, content=f"Tool failed: {e}"))

            continue

        assistant_text = (response.assistant_text or "").strip()
        messages.append(ChatMessage(role="assistant", content=assistant_text))
        await emit("assistant_message", {"content": assistant_text})
        return assistant_text, messages

    await emit("error", {"message": f"Stopped after max_steps={max_steps}."})
    return f"Stopped after max_steps={max_steps}.", messages
