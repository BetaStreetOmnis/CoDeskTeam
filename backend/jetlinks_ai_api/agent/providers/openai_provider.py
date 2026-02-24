from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re

import httpx

from ..types import ChatMessage, ToolCall
from ..tools.base import ToolDefinition
from .base import ModelResponse


_V1_RE = re.compile(r"/v1(?:$|/)")
_IMAGE_FILE_ID_RE = re.compile(r"^[a-f0-9]{32}\\.(png|jpe?g|webp|gif)$", re.IGNORECASE)
_IMAGE_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
_MAX_INPUT_IMAGES = 4
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_STRICT_GATEWAY_HINTS = {"tabcode"}
_TOOL_RESULT_START = "<<<AISTAFF_TOOL_RESULT>>>"
_TOOL_RESULT_END = "<<<END_AISTAFF_TOOL_RESULT>>>"


def _normalize_openai_base_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return base
    if _V1_RE.search(base):
        return base
    return f"{base}/v1"


def _escape_newlines(value: str) -> str:
    # Workaround for some gateways that incorrectly embed raw newlines in streamed JSON.
    # Ensure strings contain literal "\\n" rather than actual "\n" characters.
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("\n", "\\n")


def _sanitize_strings(obj: object) -> object:
    if isinstance(obj, str):
        return _escape_newlines(obj)
    if isinstance(obj, list):
        return [_sanitize_strings(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _sanitize_strings(v) for k, v in obj.items()}
    return obj


def _likely_strict_gateway(base_url: str) -> bool:
    lowered = (base_url or "").lower()
    return any(h in lowered for h in _STRICT_GATEWAY_HINTS)


def _messages_to_prompt(messages: list[ChatMessage]) -> str:
    tool_name_by_id: dict[str, str] = {}
    for m in messages:
        if m.role != "assistant" or not m.tool_calls:
            continue
        for tc in m.tool_calls:
            tc_id = str(tc.get("id") or "").strip()
            fn = tc.get("function") or {}
            name = str((fn.get("name") if isinstance(fn, dict) else "") or "").strip()
            if tc_id and name:
                tool_name_by_id[tc_id] = name

    lines: list[str] = []
    for m in messages:
        content = (m.content or "").strip()

        if m.role == "system":
            if content:
                lines.append(f"SYSTEM:\n{content}")
            continue

        if m.role == "user":
            lines.append(f"USER:\n{content}")
            if m.attachments:
                image_fids: list[str] = []
                file_refs: list[str] = []
                for a in m.attachments:
                    if not isinstance(a, dict):
                        continue
                    fid = str(a.get("file_id") or "").strip()
                    filename = str(a.get("filename") or "").strip()
                    kind = str(a.get("kind") or a.get("type") or "").strip().lower()
                    if not fid:
                        continue
                    if not kind or kind == "image":
                        image_fids.append(fid)
                    else:
                        file_refs.append(f"{filename}({fid})" if filename else fid)
                if image_fids:
                    lines.append("USER_ATTACHMENTS: " + ", ".join(image_fids))
                if file_refs:
                    lines.append("USER_FILES: " + ", ".join(file_refs))
            continue

        if m.role == "assistant":
            if content:
                lines.append(f"ASSISTANT:\n{content}")
            if m.tool_calls:
                for tc in m.tool_calls:
                    tc_id = str(tc.get("id") or "").strip()
                    fn = tc.get("function") or {}
                    name = str((fn.get("name") if isinstance(fn, dict) else "") or "").strip()
                    args = str((fn.get("arguments") if isinstance(fn, dict) else "") or "").strip() or "{}"
                    if tc_id and name:
                        lines.append(f"ASSISTANT_TOOL_CALL id={tc_id} name={name} args={args}")
            continue

        if m.role == "tool":
            tc_id = str(m.tool_call_id or "").strip()
            tool_name = tool_name_by_id.get(tc_id)
            header = f"TOOL_RESULT id={tc_id}" + (f" name={tool_name}" if tool_name else "")
            if content:
                lines.append(f"{header}:\n{_TOOL_RESULT_START}\n{content}\n{_TOOL_RESULT_END}")
            else:
                lines.append(f"{header}:\n{_TOOL_RESULT_START}\n{_TOOL_RESULT_END}")
            continue

    return "\n\n".join(lines).strip()


def _messages_to_instructions(messages: list[ChatMessage]) -> str:
    parts: list[str] = []
    for m in messages:
        if m.role != "system":
            continue
        content = (m.content or "").strip()
        if content:
            parts.append(content)
    return "\n\n".join(parts).strip()


def _extract_image_file_ids(messages: list[ChatMessage]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()

    for m in reversed(messages):
        if m.role != "user" or not m.attachments:
            continue
        for a in m.attachments:
            if not isinstance(a, dict):
                continue
            kind = str(a.get("kind") or a.get("type") or "").strip().lower()
            if kind and kind != "image":
                continue
            fid = str(a.get("file_id") or "").strip()
            if not fid or fid in seen:
                continue
            if not _IMAGE_FILE_ID_RE.match(fid):
                continue
            ids.append(fid)
            seen.add(fid)
            if len(ids) >= _MAX_INPUT_IMAGES:
                break
        if len(ids) >= _MAX_INPUT_IMAGES:
            break

    return list(reversed(ids))


def _build_image_parts(file_ids: list[str], outputs_dir: Path | None) -> list[dict]:
    if not outputs_dir or not file_ids:
        return []

    parts: list[dict] = []
    base = outputs_dir.resolve()
    total_bytes = 0

    for fid in file_ids:
        ext = Path(fid).suffix.lower()
        mime = _IMAGE_MIME_BY_EXT.get(ext)
        if not mime:
            continue

        path = (base / fid).resolve()
        if path == base or not str(path).startswith(str(base) + os.sep):
            continue
        if not path.exists() or not path.is_file():
            continue

        data = path.read_bytes()
        if not data:
            continue
        if len(data) > _MAX_IMAGE_BYTES:
            continue
        total_bytes += len(data)
        if total_bytes > _MAX_INPUT_IMAGES * _MAX_IMAGE_BYTES:
            break

        b64 = base64.b64encode(data).decode("ascii")
        parts.append({"type": "input_image", "image_url": f"data:{mime};base64,{b64}"})

    return parts


def _extract_responses_text(data: dict) -> str | None:
    out = data.get("output") or []
    if not isinstance(out, list):
        return None
    parts: list[str] = []
    for item in out:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        content = item.get("content") or []
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") not in {"output_text", "text"}:
                continue
            text = str(c.get("text") or "").strip()
            if text:
                parts.append(text)
    joined = "\n\n".join(parts).strip()
    return joined if joined else None


def _extract_responses_tool_calls(data: dict) -> list[ToolCall]:
    out = data.get("output") or []
    if not isinstance(out, list):
        return []
    tool_calls: list[ToolCall] = []
    for item in out:
        if not isinstance(item, dict):
            continue
        if item.get("type") not in {"function_call", "tool_call"}:
            continue
        call_id = str(item.get("call_id") or item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        args = str(item.get("arguments") or "{}")
        if not call_id or not name:
            continue
        tool_calls.append(ToolCall(id=call_id, name=name, arguments_json=args))
    return tool_calls


async def _collect_sse_response(res: httpx.Response) -> dict | None:
    """
    Collect the final `response` object from an OpenAI Responses streaming response.

    Many gateways (e.g. tabcode) require `stream=true` and return `text/event-stream`.
    This parser keeps the latest `response` object seen in SSE events and returns it
    when the stream ends.
    """

    last_response: dict | None = None
    data_lines: list[str] = []

    async for raw_line in res.aiter_lines():
        line = raw_line.strip("\r")
        if not line:
            if data_lines:
                payload = "\n".join(data_lines).strip()
                data_lines = []
                if not payload or payload == "[DONE]":
                    continue
                try:
                    data = json.loads(payload)
                except Exception:
                    continue

                resp = data.get("response") if isinstance(data, dict) else None
                if isinstance(resp, dict):
                    last_response = resp
            continue

        if line.startswith("data:"):
            data_lines.append(line[len("data:") :].lstrip())

    return last_response


@dataclass(frozen=True)
class OpenAiProvider:
    name: str = "openai"
    api_key: str | None = None
    base_url: str = "https://api.openai.com/v1"
    outputs_dir: Path | None = None

    async def complete(self, *, model: str, messages: list[ChatMessage], tools: list[ToolDefinition]) -> ModelResponse:
        if not self.api_key:
            raise ValueError("Missing OPENAI_API_KEY")

        base = _normalize_openai_base_url(self.base_url)
        if not base:
            raise ValueError("Missing OPENAI_BASE_URL")

        instructions = _messages_to_instructions(messages)
        if not instructions:
            # Some OpenAI-compatible gateways require non-empty instructions.
            instructions = "You are a helpful assistant."

        # Many gateways that implement Responses API expect `input` to be a list.
        # We keep a simple, robust textual transcript as a single user input item.
        prompt_messages = [m for m in messages if m.role != "system"]
        prompt = _messages_to_prompt(prompt_messages)
        image_file_ids = _extract_image_file_ids(prompt_messages)
        image_parts = _build_image_parts(image_file_ids, self.outputs_dir)
        input_content: object = prompt
        if image_parts:
            input_content = [{"type": "input_text", "text": prompt}, *image_parts]

        # Responses API tool schema (name/description/parameters at top-level).
        tools_payload_responses: list[dict] = [
            {
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters_schema,
            }
            for t in tools
        ]

        # Chat Completions API tool schema (nested under "function").
        tools_payload_chat = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters_schema,
                },
            }
            for t in tools
        ]

        strict_gateway = _likely_strict_gateway(base)

        def _responses_payload(*, strict: bool) -> dict:
            payload: dict = {
                "model": model,
                "instructions": _escape_newlines(instructions) if strict else instructions,
                "input": [{"role": "user", "content": input_content}],
                "tools": (_sanitize_strings(tools_payload_responses) if strict else tools_payload_responses),
                "tool_choice": "auto",
                "stream": True,
            }
            return payload

        async with httpx.AsyncClient(timeout=120) as client:
            async def _call_responses(*, strict: bool) -> tuple[int, dict | None]:
                async with client.stream(
                    "POST",
                    f"{base}/responses",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=_responses_payload(strict=strict),
                ) as res:
                    if res.status_code == 404:
                        return res.status_code, None
                    if res.status_code >= 400:
                        text = (await res.aread()).decode("utf-8", errors="replace")
                        raise RuntimeError(f"OpenAI error {res.status_code}: {text}")

                    ctype = (res.headers.get("content-type") or "").lower()
                    if "text/event-stream" in ctype:
                        return res.status_code, await _collect_sse_response(res)
                    # Some gateways may ignore stream=true and return JSON.
                    return res.status_code, res.json()

            status, res_data = await _call_responses(strict=strict_gateway)
            # If the gateway returned SSE but we couldn't parse a final response object,
            # retry once with strict string sanitization to keep streamed JSON parseable.
            if status < 400 and status != 404 and res_data is None and not strict_gateway:
                _status2, res_data2 = await _call_responses(strict=True)
                if res_data2 is not None:
                    res_data = res_data2

            if status == 404:
                # Fallback to Chat Completions API.
                res = await client.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": model,
                        "messages": [m.to_openai() for m in messages],
                        "tools": tools_payload_chat,
                        "tool_choice": "auto",
                    },
                )

                text = res.text
                if res.status_code >= 400:
                    raise RuntimeError(f"OpenAI error {res.status_code}: {text}")

                data = res.json()

                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}

                assistant_text = message.get("content")
                tool_calls_raw = message.get("tool_calls") or []
                tool_calls: list[ToolCall] = []
                for tc in tool_calls_raw:
                    tool_calls.append(
                        ToolCall(
                            id=str(tc.get("id") or ""),
                            name=str(((tc.get("function") or {}).get("name")) or ""),
                            arguments_json=str(((tc.get("function") or {}).get("arguments")) or "{}"),
                        )
                    )

                return ModelResponse(assistant_text=assistant_text, tool_calls=tool_calls)

            if res_data is None:
                raise RuntimeError("OpenAI Responses API stream ended without a final response object")

        assistant_text = _extract_responses_text(res_data or {})
        tool_calls = _extract_responses_tool_calls(res_data or {})
        return ModelResponse(assistant_text=assistant_text, tool_calls=tool_calls)
