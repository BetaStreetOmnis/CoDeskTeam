from __future__ import annotations

import asyncio
import json
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from ..session_store import SessionState


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 14)] + "\n…(truncated)"


def _history_text(messages: list[dict]) -> str:
    lines: list[str] = []
    for m in messages[-16:]:
        role = str(m.get("role") or "").strip()
        content = str(m.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        who = "用户" if role == "user" else "助手"
        lines.append(f"{who}：{_truncate(content, 2000)}")
    return "\n\n".join(lines).strip()


def _build_prompt(*, role: str, message: str, system_prompt: str | None, history_messages: list[dict]) -> str:
    parts: list[str] = [
        "你正在 JetLinks AI 中作为 Claude Code 执行任务。",
        f"当前角色：{role}。",
        "请直接给出最终结果。",
    ]
    extra = (system_prompt or "").strip()
    if extra:
        parts.append(f"附加系统约束（必须遵守）：\n{extra}")
    history = _history_text(history_messages)
    if history:
        parts.append(f"历史对话（供上下文参考）：\n{history}")
    parts.append(f"当前用户请求：\n{message.strip()}")
    return "\n\n".join(parts).strip()


@dataclass(frozen=True)
class ClaudeChatResult:
    assistant: str
    events: list[dict]


class ClaudeService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _resolve_command(self) -> list[str]:
        raw = (self._settings.claude_command or "claude").strip()
        parts = shlex.split(raw) if raw else ["claude"]
        if not parts:
            parts = ["claude"]
        cmd0 = parts[0]
        if "/" in cmd0 or "\\" in cmd0:
            p = Path(cmd0).expanduser()
            if not p.exists():
                raise ValueError(f"Claude command not found: {p}")
            parts[0] = str(p)
            return parts
        resolved = shutil.which(cmd0)
        if not resolved:
            raise ValueError("Claude Code CLI not found. Please install it and set JETLINKS_AI_CLAUDE_CMD.")
        parts[0] = resolved
        return parts

    def _timeout_seconds(self) -> int:
        return max(10, int(self._settings.claude_timeout_seconds))

    async def chat(
        self,
        *,
        session: SessionState,
        message: str,
        role: str,
        model: str | None,
        workspace_root: Path,
        system_prompt: str | None,
    ) -> ClaudeChatResult:
        cmd = self._resolve_command()
        workspace = workspace_root.resolve()
        used_model = (model or self._settings.claude_model or "glm-4.7").strip() or "glm-4.7"
        prompt = _build_prompt(
            role=role,
            message=message,
            system_prompt=system_prompt,
            history_messages=[{"role": m.role, "content": m.content} for m in session.messages],
        )

        args = [
            *cmd,
            "-p",
            "--output-format",
            "json",
            "--model",
            used_model,
            prompt,
        ]
        started = asyncio.get_event_loop().time()
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
            raise ValueError(f"Claude timed out after {self._timeout_seconds()}s") from e

        stdout = stdout_b.decode("utf-8", errors="ignore").strip()
        stderr = stderr_b.decode("utf-8", errors="ignore").strip()
        if proc.returncode != 0:
            err = stderr or stdout or "unknown error"
            raise ValueError(f"Claude command failed (exit={proc.returncode}): {err}")

        try:
            obj = json.loads(stdout.splitlines()[-1] if "\n" in stdout else stdout)
        except Exception:
            obj = {}
        assistant = str(obj.get("result") or "").strip() or stdout or "（Claude 未返回可显示文本）"
        events = [
            {
                "type": "claude_done",
                "model": used_model,
                "elapsed_ms": int((asyncio.get_event_loop().time() - started) * 1000),
            }
        ]
        if stderr:
            events.insert(0, {"type": "claude_warning", "message": _truncate(stderr, 1200)})
        return ClaudeChatResult(assistant=assistant, events=events)

