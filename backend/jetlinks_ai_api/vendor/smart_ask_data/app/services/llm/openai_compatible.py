from __future__ import annotations

import json
import re

import httpx

from app.services.llm.base import LLMClient


def _normalize_wire_api(value: str) -> str:
    raw = (value or "").strip().lower()
    if raw in {"responses", "response"}:
        return "responses"
    if raw in {"chat", "chat_completions", "chat-completions", "chatcompletions"}:
        return "chat_completions"
    if raw == "auto":
        return "auto"
    return "chat_completions"


class OpenAICompatibleLLM(LLMClient):
    def __init__(self, base_url: str, api_key: str, model: str, *, wire_api: str = "chat_completions") -> None:
        base = (base_url or "").strip().rstrip("/")
        if base.lower().endswith("/v1"):
            base = base[:-3]
        self._base_url = base.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._wire_api = _normalize_wire_api(wire_api)

    async def _chat_completions(self, *, messages: list[dict], max_tokens: int, temperature: float) -> str:
        url = f"{self._base_url}/v1/chat/completions"
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()

    async def _responses(self, *, instructions: str, input_messages: list[dict]) -> str:
        instructions = (instructions or "").strip() or "You are a helpful assistant."
        if not input_messages:
            input_messages = [{"role": "user", "content": ""}]

        payload = {
            "model": self._model,
            "instructions": instructions,
            "input": input_messages,
            # Tabcode requires stream=true; keep it on and aggregate deltas.
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "text/event-stream",
        }

        # Prefer /responses (Tabcode), fall back to /v1/responses (OpenAI).
        urls = [f"{self._base_url}/responses", f"{self._base_url}/v1/responses"]

        async with httpx.AsyncClient(timeout=120.0) as client:
            last_error: Exception | None = None
            for url in urls:
                try:
                    async with client.stream("POST", url, headers=headers, json=payload) as resp:
                        if resp.status_code == 404:
                            continue
                        resp.raise_for_status()
                        content_type = (resp.headers.get("content-type") or "").lower()
                        if "text/event-stream" not in content_type:
                            try:
                                data = await resp.aread()
                                obj = json.loads(data.decode("utf-8", errors="replace") or "{}")
                            except Exception:
                                return ""
                            return _extract_responses_text(obj)
                        return await _collect_responses_sse(resp)
                except Exception as e:
                    last_error = e
                    continue
            raise last_error or RuntimeError("OpenAI Responses 请求失败")

    async def chat(self, question: str, history: list[dict]) -> str:
        if not self._base_url or not self._api_key:
            raise RuntimeError("OpenAI兼容接口未配置：SMARTASK_OPENAI_BASE_URL / SMARTASK_OPENAI_API_KEY")

        history_msgs: list[dict] = []
        if history:
            tail = history[-6:]
            for m in tail:
                role = (m.get("role") or "").strip().lower()
                if role not in {"user", "assistant", "system"}:
                    role = "user"
                content = (m.get("content") or "").strip()
                if content:
                    history_msgs.append({"role": role, "content": content})

        messages = [
            {
                "role": "system",
                "content": (
                    "你是智能问数助手，负责自然、简短地回答用户。"
                    "用户只是问候/寒暄/感谢/告别时，简洁友好回应；"
                    "如用户表达查询意图，提醒可直接提问数据需求。"
                    "不要编造具体数据。"
                ),
            },
            *history_msgs,
        ]

        question = (question or "").strip()
        if question and (
            not history_msgs
            or history_msgs[-1].get("role") != "user"
            or history_msgs[-1].get("content") != question
        ):
            messages.append({"role": "user", "content": question})

        if self._wire_api == "responses":
            system_text = str(messages[0].get("content") or "") if messages else ""
            input_messages = [m for m in messages[1:] if m.get("content")]
            return await self._responses(instructions=system_text, input_messages=input_messages)
        return await self._chat_completions(messages=messages, temperature=0.7, max_tokens=200)

    async def explain_sql(self, question: str, sql: str) -> str:
        if not self._base_url or not self._api_key:
            raise RuntimeError("OpenAI兼容接口未配置：SMARTASK_OPENAI_BASE_URL / SMARTASK_OPENAI_API_KEY")

        user_content = (
            f"问题：{(question or '').strip()}\n"
            f"SQL：\n{(sql or '').strip()}\n\n"
            "请输出一段更详细的「SQL 说明」，要求：\n"
            "1) 用 6-10 条要点（每条 1 句，尽量具体）。\n"
            "2) 覆盖：数据来源表/视图；统计口径（COUNT 是否需要 DISTINCT/去重）；分组维度；过滤条件(WHERE/HAVING)；"
            "排序与 Top-N（ORDER BY/LIMIT）；时间字段/时区/毫秒转换；输出字段含义；可能的口径陷阱与改进建议。\n"
            "3) 表名/字段名用反引号包裹（例如 `fire_alarm_record`、`unit_name`）。\n"
            "4) 不要编造实际数据，不要输出推理过程或中间步骤。"
        )

        messages = [
            {
                "role": "system",
                "content": "你是SQL助手，只输出简短说明文本。",
            },
            {"role": "user", "content": user_content},
        ]
        if self._wire_api == "responses":
            system_text = str(messages[0].get("content") or "")
            input_messages = [m for m in messages[1:] if m.get("content")]
            return await self._responses(instructions=system_text, input_messages=input_messages)
        return await self._chat_completions(messages=messages, temperature=0.2, max_tokens=200)

    async def generate_sql(self, prompt: str) -> str:
        if not self._base_url or not self._api_key:
            raise RuntimeError("OpenAI兼容接口未配置：SMARTASK_OPENAI_BASE_URL / SMARTASK_OPENAI_API_KEY")

        messages = [
            {
                "role": "system",
                "content": "你是SQL专家。只输出SQL（SELECT查询），不要解释。",
            },
            {"role": "user", "content": prompt},
        ]
        if self._wire_api == "responses":
            system_text = str(messages[0].get("content") or "")
            input_messages = [m for m in messages[1:] if m.get("content")]
            return await self._responses(instructions=system_text, input_messages=input_messages)
        return await self._chat_completions(messages=messages, temperature=0.1, max_tokens=600)

    async def classify_intent(self, question: str, history: list[dict]) -> str:
        if not self._base_url or not self._api_key:
            raise RuntimeError("OpenAI兼容接口未配置：SMARTASK_OPENAI_BASE_URL / SMARTASK_OPENAI_API_KEY")

        history_text = ""
        if history:
            tail = history[-6:]
            history_text = "\n".join(
                f"{(m.get('role') or '').strip()}: {(m.get('content') or '').strip()}"
                for m in tail
                if (m.get("content") or "").strip()
            )

        user_content = ""
        if history_text:
            user_content += f"对话历史：\n{history_text}\n\n"
        user_content += f"问题：{question}\n只输出 chat 或 data。"

        messages = [
            {
                "role": "system",
                "content": (
                    "你是意图分类器，只输出一个词：chat 或 data。"
                    "chat=闲聊问候/寒暄/感谢/告别；"
                    "data=查询数据/统计/图表/SQL/表字段。"
                    "无法判断时输出 data。"
                ),
            },
            {"role": "user", "content": user_content},
        ]
        if self._wire_api == "responses":
            system_text = str(messages[0].get("content") or "")
            input_messages = [m for m in messages[1:] if m.get("content")]
            content = (await self._responses(instructions=system_text, input_messages=input_messages)).strip()
            return _parse_intent(content)
        content = (await self._chat_completions(messages=messages, temperature=0.0, max_tokens=8)).strip()
        return _parse_intent(content)


def _parse_intent(text: str) -> str:
    raw = (text or "").strip().lower()
    if not raw:
        return "unknown"

    m = re.search(r"\b(chat|data)\b", raw)
    if m:
        return m.group(1)

    if any(k in raw for k in ["闲聊", "聊天", "问候", "寒暄", "感谢", "致谢", "告别", "打招呼"]):
        return "chat"
    if any(k in raw for k in ["查询", "数据", "图表", "统计", "sql", "表", "字段"]):
        return "data"
    return "unknown"


async def _collect_responses_sse(resp: httpx.Response) -> str:
    chunks: list[str] = []
    final_text: str | None = None
    current_event: str | None = None
    data_buf: list[str] = []

    async for raw in resp.aiter_lines():
        line = (raw or "").strip()
        if not line:
            if not data_buf:
                current_event = None
                continue
            data_str = "\n".join(data_buf).strip()
            data_buf = []

            if data_str == "[DONE]":
                break

            obj: dict | None = None
            try:
                parsed = json.loads(data_str)
                obj = parsed if isinstance(parsed, dict) else None
            except Exception:
                obj = None

            event_type = current_event or (obj.get("type") if obj else None)
            if event_type == "response.output_text.delta" and obj:
                delta = obj.get("delta")
                if isinstance(delta, str) and delta:
                    chunks.append(delta)
            elif event_type == "response.output_text.done" and obj:
                text = obj.get("text")
                if isinstance(text, str):
                    final_text = text
            elif event_type in {"response.completed", "response.done"}:
                break
            elif event_type in {"response.failed", "response.error"}:
                raise RuntimeError("OpenAI Responses 返回失败")

            current_event = None
            continue

        if line.startswith("event:"):
            current_event = line[6:].strip()
            continue
        if line.startswith("data:"):
            data_buf.append(line[5:].lstrip())
            continue

    if chunks:
        return "".join(chunks).strip()
    if final_text is not None:
        return final_text.strip()
    return ""


def _extract_responses_text(obj: dict) -> str:
    # Best-effort parsing when provider returns non-stream JSON.
    try:
        output = obj.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, dict) or item.get("type") != "message":
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for p in content:
                    if isinstance(p, dict) and p.get("type") == "output_text":
                        text = p.get("text")
                        if isinstance(text, str) and text:
                            parts.append(text)
            if parts:
                return "\n".join(parts).strip()
    except Exception:
        pass
    return ""
