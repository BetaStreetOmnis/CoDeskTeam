from __future__ import annotations

import asyncio
import json
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Settings
from ..session_store import SessionState


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 14)] + "\n…(truncated)"


def _history_text(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for m in messages[-16:]:
        role = str(m.get("role") or "").strip()
        content = str(m.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        who = "用户" if role == "user" else "助手"
        lines.append(f"{who}：{_truncate(content, 1200)}")
    return "\n\n".join(lines).strip()


def _build_prompt(*, role: str, message: str, system_prompt: str | None, history_messages: list[dict[str, Any]]) -> str:
    parts: list[str] = [
        "你正在 JetLinks AI 中作为 OpenClaw 执行任务。",
        f"当前角色：{role}。",
        "请优先返回可执行结果，避免空泛表述。",
    ]
    extra = (system_prompt or "").strip()
    if extra:
        parts.append(f"附加系统约束（必须遵守）：\n{extra}")
    history = _history_text(history_messages)
    if history:
        parts.append(f"历史对话（供上下文参考）：\n{history}")
    parts.append(f"当前用户请求：\n{message.strip()}")
    return "\n\n".join(parts).strip()


def _extract_json_obj(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    for ln in reversed(lines):
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def _extract_payload_text(obj: dict[str, Any]) -> str:
    payloads = obj.get("payloads")
    if not isinstance(payloads, list):
        return ""
    chunks: list[str] = []
    for item in payloads:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if text:
            chunks.append(text)
    return "\n\n".join(chunks).strip()


def _extract_error_text(obj: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key in ("error", "message", "detail", "summary", "reason"):
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            chunks.append(value.strip())
        elif isinstance(value, dict):
            inner = str(value.get("message") or value.get("detail") or "").strip()
            if inner:
                chunks.append(inner)
    payload_text = _extract_payload_text(obj)
    if payload_text:
        chunks.append(payload_text)
    seen: set[str] = set()
    out: list[str] = []
    for item in chunks:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return "\n".join(out).strip()


def _best_error(stderr: str, stdout: str) -> str:
    parts: list[str] = []
    for raw in (stderr, stdout):
        text = (raw or "").strip()
        if not text:
            continue
        obj = _extract_json_obj(text)
        extracted = _extract_error_text(obj) if isinstance(obj, dict) else ""
        if extracted:
            parts.append(extracted)
        elif text:
            parts.append(_truncate(text, 1200))
    merged = "\n".join([p for p in parts if p]).strip()
    if merged:
        return merged
    return "no stderr/stdout (可能是网关异常关闭或模型鉴权失败)"


def _is_transient_openclaw_error(text: str) -> bool:
    t = (text or "").lower()
    if not t:
        return False
    markers = (
        "no stderr/stdout",
        "gateway closed",
        "connection error",
        "econnreset",
        "abnormal closure",
        "timed out",
    )
    return any(m in t for m in markers)


@dataclass(frozen=True)
class OpenClawChatResult:
    assistant: str
    openclaw_session_id: str | None
    events: list[dict[str, Any]]


class OpenClawService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _resolve_command(self) -> list[str]:
        raw = (self._settings.openclaw_command or "openclaw").strip()
        parts = shlex.split(raw) if raw else ["openclaw"]
        if not parts:
            parts = ["openclaw"]
        cmd0 = parts[0]
        if "/" in cmd0 or "\\" in cmd0:
            p = Path(cmd0).expanduser()
            if not p.exists():
                raise ValueError(f"OpenClaw command not found: {p}")
            parts[0] = str(p)
            return parts
        resolved = shutil.which(cmd0)
        if not resolved:
            raise ValueError("OpenClaw CLI not found. Please install it and set JETLINKS_AI_OPENCLAW_CMD.")
        parts[0] = resolved
        return parts

    def _timeout_seconds(self) -> int:
        return max(10, int(self._settings.openclaw_timeout_seconds))

    def _max_attempts(self) -> int:
        return 2

    async def chat(
        self,
        *,
        session: SessionState,
        message: str,
        role: str,
        model: str | None,
        workspace_root: Path,
        system_prompt: str | None,
    ) -> OpenClawChatResult:
        if not bool(self._settings.openclaw_enabled):
            raise ValueError("OpenClaw provider is disabled by server config.")

        cmd = self._resolve_command()
        workspace = workspace_root.resolve()
        used_model = (model or self._settings.model or "").strip()
        prompt = _build_prompt(
            role=role,
            message=message,
            system_prompt=system_prompt,
            history_messages=[{"role": m.role, "content": m.content} for m in session.messages],
        )

        args = [*cmd, "agent", "--message", prompt, "--session-id", session.session_id, "--json"]

        started = asyncio.get_event_loop().time()
        stdout = ""
        stderr = ""
        last_err = ""
        for attempt in range(1, self._max_attempts() + 1):
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=self._timeout_seconds())
            except asyncio.TimeoutError as e:
                try:
                    proc.kill()
                except Exception:
                    pass
                last_err = f"OpenClaw timed out after {self._timeout_seconds()}s"
                if attempt < self._max_attempts():
                    await asyncio.sleep(0.6)
                    continue
                raise ValueError(last_err) from e

            stdout = stdout_b.decode("utf-8", errors="ignore").strip()
            stderr = stderr_b.decode("utf-8", errors="ignore").strip()
            if proc.returncode == 0:
                break

            err = _best_error(stderr, stdout)
            last_err = f"OpenClaw command failed (exit={proc.returncode}): {err}"
            if attempt < self._max_attempts() and _is_transient_openclaw_error(err):
                await asyncio.sleep(0.6)
                continue
            raise ValueError(last_err)

        obj = _extract_json_obj(stdout) or {}
        assistant = (
            _extract_payload_text(obj)
            or str(obj.get("result") or "").strip()
            or str(obj.get("message") or "").strip()
            or str(obj.get("response") or "").strip()
            or stdout
            or "（OpenClaw 未返回可显示文本）"
        )
        openclaw_session_id = (
            str(obj.get("sessionId") or "").strip()
            or str(obj.get("session_id") or "").strip()
            or session.session_id
        )
        events: list[dict[str, Any]] = [
            {
                "type": "openclaw_done",
                "model": used_model or None,
                "elapsed_ms": int((asyncio.get_event_loop().time() - started) * 1000),
            }
        ]
        if stderr:
            events.insert(0, {"type": "openclaw_warning", "message": _truncate(stderr, 1200)})
        return OpenClawChatResult(assistant=assistant, openclaw_session_id=openclaw_session_id, events=events)
