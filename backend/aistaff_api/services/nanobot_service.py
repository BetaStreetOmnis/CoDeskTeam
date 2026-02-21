from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Settings
from ..session_store import SessionState


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 14)] + "\n…(truncated)"


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def _extract_assistant_text(stdout: str, stderr: str) -> str:
    cleaned = _strip_ansi(stdout)
    lines = [line.rstrip() for line in cleaned.splitlines()]
    lines = [line for line in lines if line.strip()]
    if not lines:
        return _strip_ansi(stderr).strip()

    marker_idx = -1
    for i, line in enumerate(lines):
        if "nanobot" in line.lower():
            marker_idx = i
    if marker_idx >= 0 and marker_idx + 1 < len(lines):
        text = "\n".join(lines[marker_idx + 1 :]).strip()
        if text:
            return text

    return "\n".join(lines).strip()


@dataclass(frozen=True)
class NanobotChatResult:
    assistant: str
    events: list[dict[str, Any]]


class NanobotService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _home_dir(self) -> Path:
        return self._settings.nanobot_home_dir.resolve()

    def _config_path(self) -> Path:
        return self._home_dir() / ".nanobot" / "config.json"

    def _timeout_seconds(self) -> int:
        return max(5, int(self._settings.nanobot_timeout_seconds))

    def _resolve_command(self) -> list[str]:
        raw = (self._settings.nanobot_command or "nanobot").strip()
        parts = shlex.split(raw) if raw else ["nanobot"]
        if not parts:
            parts = ["nanobot"]

        cmd0 = parts[0]
        if "/" in cmd0 or "\\" in cmd0:
            p = Path(cmd0).expanduser()
            if not p.exists():
                raise ValueError(f"Nanobot command not found: {p}")
            parts[0] = str(p)
            return parts

        resolved = shutil.which(cmd0)
        if not resolved:
            raise ValueError(
                "Nanobot CLI not found. Please install it first: `pip install nanobot-ai` "
                "or set AISTAFF_NANOBOT_CMD to an executable path."
            )
        parts[0] = resolved
        return parts

    def _build_config(self, *, workspace_root: Path, model: str | None) -> dict[str, Any]:
        api_key = (self._settings.openai_api_key or "").strip()
        if not api_key:
            raise ValueError("Nanobot requires OPENAI_API_KEY to be configured.")

        model_name = (model or self._settings.model or "gpt-5.2").strip() or "gpt-5.2"
        return {
            "providers": {
                "openai": {
                    "apiKey": api_key,
                    "apiBase": (self._settings.openai_base_url or "https://api.openai.com/v1").strip(),
                }
            },
            "agents": {
                "defaults": {
                    "workspace": str(workspace_root),
                    "model": model_name,
                    "maxToolIterations": max(1, int(self._settings.max_steps)),
                }
            },
            "tools": {
                "restrictToWorkspace": True,
                "exec": {"timeout": 60},
            },
            "channels": {},
            "gateway": {"host": "127.0.0.1", "port": 18790},
        }

    def _ensure_config(self, *, workspace_root: Path, model: str | None) -> Path:
        cfg_path = self._config_path()
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        config = self._build_config(workspace_root=workspace_root, model=model)
        cfg_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        return cfg_path

    async def chat(
        self,
        *,
        session: SessionState,
        message: str,
        role: str,
        model: str | None,
        workspace_root: Path,
        enable_shell: bool,
        enable_write: bool,
        system_prompt: str | None,
    ) -> NanobotChatResult:
        cmd = self._resolve_command()
        cfg_path = self._ensure_config(workspace_root=workspace_root, model=model)

        user_input = (message or "").strip()
        if system_prompt and system_prompt.strip():
            user_input = (
                "请严格遵守以下补充要求后再完成任务：\n"
                f"{system_prompt.strip()}\n\n"
                "用户原始请求：\n"
                f"{user_input}"
            )

        session_key = f"aistaff:{session.session_id}"
        args = [
            *cmd,
            "agent",
            "-m",
            user_input,
            "--session",
            session_key,
            "--no-markdown",
            "--no-logs",
        ]

        env = os.environ.copy()
        env["HOME"] = str(self._home_dir())
        env["PYTHONIOENCODING"] = "utf-8"

        events: list[dict[str, Any]] = [
            {
                "type": "nanobot_start",
                "workspace": str(workspace_root),
                "role": role,
                "model": model,
                "command": " ".join(args[:2]),
                "config": str(cfg_path),
                "tools_requested": {"shell": bool(enable_shell), "write": bool(enable_write)},
            }
        ]

        started_at = time.time()
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(workspace_root),
            env=env,
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
            raise ValueError(f"Nanobot timed out after {self._timeout_seconds()}s") from e

        stdout = stdout_b.decode("utf-8", errors="ignore")
        stderr = stderr_b.decode("utf-8", errors="ignore")

        if proc.returncode != 0:
            err = _strip_ansi(stderr).strip() or _strip_ansi(stdout).strip()
            raise ValueError(
                f"Nanobot command failed (exit={proc.returncode}): {_truncate(err or 'unknown error', 800)}"
            )

        assistant = _extract_assistant_text(stdout, stderr)
        if not assistant:
            assistant = "（Nanobot 未返回可显示的文本输出）"

        events.append(
            {
                "type": "nanobot_done",
                "elapsed_ms": int((time.time() - started_at) * 1000),
                "stdout_preview": _truncate(_strip_ansi(stdout), 1200),
            }
        )
        return NanobotChatResult(assistant=assistant, events=events)
