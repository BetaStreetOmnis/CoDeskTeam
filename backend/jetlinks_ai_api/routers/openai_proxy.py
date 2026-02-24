from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, AsyncIterator
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask

from ..deps import get_settings


router = APIRouter(tags=["openai-proxy"])

_V1_RE = re.compile(r"/v1(?:$|/)")
_DEFAULT_INSTRUCTIONS = "You are a helpful assistant."
_TOOL_RESULT_START = "<<<AISTAFF_TOOL_RESULT>>>"
_TOOL_RESULT_END = "<<<END_AISTAFF_TOOL_RESULT>>>"


def _normalize_openai_base_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return base
    if _V1_RE.search(base):
        return base
    return f"{base}/v1"


def _is_localhost(host: str | None) -> bool:
    return host in {"127.0.0.1", "::1", "localhost"}


def _extract_json_detail(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return text


def _escape_newlines(value: str) -> str:
    # Workaround for some gateways that incorrectly embed raw newlines in streamed JSON.
    # Ensure strings contain literal "\\n" rather than actual "\n" characters.
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("\n", "\\n")


def _sanitize_strings(obj: Any) -> Any:
    if isinstance(obj, str):
        return _escape_newlines(obj)
    if isinstance(obj, list):
        return [_sanitize_strings(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _sanitize_strings(v) for k, v in obj.items()}
    return obj


def _extract_messages_instructions(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    parts: list[str] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "").strip() != "system":
            continue
        content = m.get("content")
        text = str(content or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _safe_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    # Best-effort: extract text from multi-modal parts.
    if isinstance(content, list):
        texts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = str(part.get("type") or "").strip().lower()
            if ptype in {"text", "input_text", "output_text"}:
                t = part.get("text")
                if isinstance(t, str) and t.strip():
                    texts.append(t)
            elif ptype in {"image", "image_url", "input_image"}:
                texts.append("[image]")
        return "\n".join(texts).strip()
    if content is None:
        return ""
    try:
        return str(content)
    except Exception:
        return ""


def _messages_to_prompt(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""

    tool_name_by_id: dict[str, str] = {}
    for m in messages:
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "").strip() != "assistant":
            continue
        for tc in m.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            tc_id = str(tc.get("id") or "").strip()
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            name = str(fn.get("name") or "").strip()
            if tc_id and name:
                tool_name_by_id[tc_id] = name

    lines: list[str] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip()
        content = _safe_message_content(m.get("content")).strip()

        if role == "user":
            lines.append(f"USER:\n{content}")
            continue

        if role == "assistant":
            if content:
                lines.append(f"ASSISTANT:\n{content}")
            for tc in m.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                tc_id = str(tc.get("id") or "").strip()
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                name = str(fn.get("name") or "").strip()
                args = str(fn.get("arguments") or "").strip() or "{}"
                if tc_id and name:
                    lines.append(f"ASSISTANT_TOOL_CALL id={tc_id} name={name} args={args}")
            continue

        if role == "tool":
            tc_id = str(m.get("tool_call_id") or "").strip()
            tool_name = tool_name_by_id.get(tc_id)
            header = f"TOOL_RESULT id={tc_id}" + (f" name={tool_name}" if tool_name else "")
            if content:
                lines.append(f"{header}:\n{_TOOL_RESULT_START}\n{content}\n{_TOOL_RESULT_END}")
            else:
                lines.append(f"{header}:\n{_TOOL_RESULT_START}\n{_TOOL_RESULT_END}")
            continue

    return "\n\n".join(lines).strip()


def _chat_tools_to_responses_tools(tools: Any) -> list[dict[str, Any]]:
    if not isinstance(tools, list):
        return []
    out: list[dict[str, Any]] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        if str(t.get("type") or "").strip() != "function":
            continue
        fn = t.get("function") if isinstance(t.get("function"), dict) else None
        if fn is not None:
            name = str(fn.get("name") or "").strip()
            if not name:
                continue
            out.append(
                {
                    "type": "function",
                    "name": name,
                    "description": str(fn.get("description") or "").strip(),
                    "parameters": fn.get("parameters") if isinstance(fn.get("parameters"), dict) else {},
                }
            )
            continue

        # Also accept Responses-style tool schemas.
        name = str(t.get("name") or "").strip()
        if not name:
            continue
        out.append(
            {
                "type": "function",
                "name": name,
                "description": str(t.get("description") or "").strip(),
                "parameters": t.get("parameters") if isinstance(t.get("parameters"), dict) else {},
            }
        )
    return out


async def _collect_sse_response(res: httpx.Response) -> dict | None:
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


def _extract_responses_text(data: dict) -> str:
    out = data.get("output") or []
    if not isinstance(out, list):
        return ""
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
    return "\n\n".join(parts).strip()


def _extract_responses_tool_calls(data: dict) -> list[dict[str, Any]]:
    out = data.get("output") or []
    if not isinstance(out, list):
        return []
    tool_calls: list[dict[str, Any]] = []
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
        tool_calls.append(
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": args},
            }
        )
    return tool_calls


@router.post("/openai/v1/responses")
async def proxy_openai_responses(request: Request, settings=Depends(get_settings)):  # noqa: ANN001
    """
    A tiny OpenAI-compatible proxy for gateways that are strict about the Responses API payload.

    Motivation:
    - Some gateways (e.g. tabcode) require non-empty `instructions` and `stream=true`.
    - OpenCode's Responses API client may omit `instructions` entirely.
    """

    if not _is_localhost(getattr(request.client, "host", None)):
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid json: {e}") from None

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid json body (expected object)")

    instructions = payload.get("instructions")
    if not isinstance(instructions, str) or not instructions.strip():
        payload["instructions"] = _DEFAULT_INSTRUCTIONS
    payload["instructions"] = _escape_newlines(str(payload.get("instructions") or ""))

    # Compatibility: some gateways require `input` to be a list (OpenAI Responses API supports
    # multiple input items). If a client sends a plain string, wrap it as a single user item.
    input_value = payload.get("input")
    if isinstance(input_value, str):
        payload["input"] = [{"role": "user", "content": input_value}]
    elif isinstance(input_value, dict):
        payload["input"] = [input_value]

    # tabcode requires stream=true; keep compatibility even if client sent false/omitted.
    payload["stream"] = True

    # Workaround: sanitize tool definitions (descriptions often contain newlines) to keep
    # gateway streaming JSON parseable by clients.
    if isinstance(payload.get("tools"), list):
        payload["tools"] = _sanitize_strings(payload["tools"])

    upstream_base = _normalize_openai_base_url(settings.openai_base_url)
    if not upstream_base:
        raise HTTPException(status_code=500, detail="Missing OPENAI_BASE_URL")
    upstream_url = f"{upstream_base}/responses"

    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        # Fallback: forward the incoming auth header if present (useful for debugging).
        forwarded_auth = (request.headers.get("authorization") or "").strip()
        if not forwarded_auth:
            raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY")
        headers = {"Authorization": forwarded_auth}
    else:
        headers = {"Authorization": f"Bearer {api_key}"}

    client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
    # Keep the context manager alive for the whole streaming response.
    # Otherwise it may get GC'd and close the upstream stream early.
    upstream_cm = client.stream("POST", upstream_url, headers=headers, json=payload)
    res = await upstream_cm.__aenter__()

    if res.status_code >= 400:
        raw = (await res.aread()).decode("utf-8", errors="replace")
        await res.aclose()
        await client.aclose()
        raise HTTPException(status_code=res.status_code, detail=_extract_json_detail(raw))

    async def _iter() -> AsyncIterator[bytes]:
        try:
            async for chunk in res.aiter_bytes():
                yield chunk
        except asyncio.CancelledError:
            # Client disconnected.
            raise
        except (httpx.ReadError, httpx.StreamError):
            # Upstream closed mid-stream; end the response gracefully.
            return

    async def _cleanup() -> None:
        try:
            await upstream_cm.__aexit__(None, None, None)
        finally:
            await client.aclose()

    content_type = (res.headers.get("content-type") or "").strip() or "application/octet-stream"
    headers_out: dict[str, str] = {}
    cache_control = (res.headers.get("cache-control") or "").strip()
    if cache_control:
        headers_out["cache-control"] = cache_control

    return StreamingResponse(
        _iter(),
        media_type=content_type,
        headers=headers_out,
        background=BackgroundTask(_cleanup),
    )


@router.post("/openai/v1/chat/completions")
async def proxy_openai_chat_completions(request: Request, settings=Depends(get_settings)):  # noqa: ANN001
    """
    Compatibility shim: translate Chat Completions requests to Responses API.

    Motivation:
    - Some OpenAI-compatible gateways (e.g. tabcode) only implement `POST /v1/responses`.
    - Some clients (or older OpenCode builds) still call `POST /v1/chat/completions`.

    Notes:
    - Upstream will always be called with `stream=true` (required by some gateways).
    - If client asks for streaming, we respond with SSE but may buffer internally.
    """

    if not _is_localhost(getattr(request.client, "host", None)):
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid json: {e}") from None

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid json body (expected object)")

    model = str(payload.get("model") or "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="missing model")

    messages = payload.get("messages")
    instructions = _extract_messages_instructions(messages)
    if not instructions:
        instructions = _DEFAULT_INSTRUCTIONS
    # Some gateways embed instructions in streamed JSON unsafely; avoid raw newlines.
    instructions = _escape_newlines(instructions)

    filtered_messages = [m for m in messages if isinstance(m, dict) and str(m.get("role") or "").strip() != "system"] if isinstance(messages, list) else []
    prompt = _messages_to_prompt(filtered_messages)
    if not prompt:
        raise HTTPException(status_code=400, detail="missing messages")

    tools_payload = _chat_tools_to_responses_tools(payload.get("tools"))
    if tools_payload:
        tools_payload = _sanitize_strings(tools_payload)

    upstream_base = _normalize_openai_base_url(settings.openai_base_url)
    if not upstream_base:
        raise HTTPException(status_code=500, detail="Missing OPENAI_BASE_URL")
    upstream_url = f"{upstream_base}/responses"

    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        forwarded_auth = (request.headers.get("authorization") or "").strip()
        if not forwarded_auth:
            raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY")
        headers = {"Authorization": forwarded_auth}
    else:
        headers = {"Authorization": f"Bearer {api_key}"}

    # tabcode requires stream=true; keep compatibility even if client sent false/omitted.
    responses_payload: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": [{"role": "user", "content": prompt}],
        "stream": True,
    }
    if tools_payload:
        responses_payload["tools"] = tools_payload
        responses_payload["tool_choice"] = payload.get("tool_choice") or "auto"

    want_stream = bool(payload.get("stream"))
    chat_id = f"chatcmpl_{uuid4().hex}"
    created = int(time.time())

    client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
    try:
        async with client.stream("POST", upstream_url, headers=headers, json=responses_payload) as res:
            if res.status_code >= 400:
                raw = (await res.aread()).decode("utf-8", errors="replace")
                raise HTTPException(status_code=res.status_code, detail=_extract_json_detail(raw))

            ctype = (res.headers.get("content-type") or "").lower()
            response_obj: dict | None
            if "text/event-stream" in ctype:
                response_obj = await _collect_sse_response(res)
            else:
                response_obj = res.json()

        if not isinstance(response_obj, dict):
            raise HTTPException(status_code=502, detail="Upstream returned invalid response")

        model_out = str(response_obj.get("model") or model).strip() or model
        assistant_text = _extract_responses_text(response_obj)
        tool_calls = _extract_responses_tool_calls(response_obj)
        finish_reason = "tool_calls" if tool_calls else "stop"

        if not want_stream:
            message: dict[str, Any] = {"role": "assistant", "content": assistant_text}
            if tool_calls:
                message["tool_calls"] = tool_calls

            body = {
                "id": chat_id,
                "object": "chat.completion",
                "created": created,
                "model": model_out,
                "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
            }
            return Response(content=json.dumps(body, ensure_ascii=False), media_type="application/json")

        async def _iter() -> AsyncIterator[bytes]:
            # Emit a minimal Chat Completions stream (buffered).
            delta: dict[str, Any] = {"role": "assistant"}
            if assistant_text:
                delta["content"] = assistant_text
            if tool_calls:
                delta["tool_calls"] = tool_calls

            chunk1 = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_out,
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
            chunk2 = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_out,
                "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
            }

            yield f"data: {json.dumps(chunk1, ensure_ascii=False)}\n\n".encode("utf-8")
            yield f"data: {json.dumps(chunk2, ensure_ascii=False)}\n\n".encode("utf-8")
            yield b"data: [DONE]\n\n"

        return StreamingResponse(
            _iter(),
            media_type="text/event-stream",
            headers={"cache-control": "no-store"},
        )
    finally:
        await client.aclose()


@router.get("/openai/v1/models")
async def proxy_openai_models(request: Request, settings=Depends(get_settings)):  # noqa: ANN001
    # Keep this minimal; some clients probe /models even if the upstream gateway doesn't implement it.
    if not _is_localhost(getattr(request.client, "host", None)):
        raise HTTPException(status_code=403, detail="forbidden")

    model_ids: list[str] = []
    configured = str(getattr(settings, "model", "") or "").strip()
    if configured:
        model_ids.append(configured)
    # Provide a sane default for clients that require at least one model in the list.
    if "gpt-5.2" not in model_ids:
        model_ids.append("gpt-5.2")

    data = [{"id": mid, "object": "model", "created": 0, "owned_by": "openai"} for mid in dict.fromkeys(model_ids)]
    return Response(content=json.dumps({"object": "list", "data": data}), media_type="application/json")
