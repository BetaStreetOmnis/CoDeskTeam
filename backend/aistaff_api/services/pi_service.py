from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..agent.types import ChatMessage
from ..config import Settings
from ..session_store import SessionState


_MAX_HISTORY_MESSAGES = 16
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 14)] + "\n…(truncated)"


def _normalize_openai_base_url(value: str) -> str:
    base = (value or "").strip().rstrip("/")
    if not base:
        return base
    if base.endswith("/v1") or "/v1/" in base:
        return base
    return f"{base}/v1"


def _history_text(messages: list[ChatMessage]) -> str:
    lines: list[str] = []
    history = [m for m in messages if m.role in {"user", "assistant"}][- _MAX_HISTORY_MESSAGES :]
    for m in history:
        role = "用户" if m.role == "user" else "助手"
        content = (m.content or "").strip()
        if not content:
            continue
        lines.append(f"{role}：{_truncate(content, 1500)}")
    return "\n\n".join(lines).strip()


def _build_user_prompt(
    *,
    role: str,
    message: str,
    history_messages: list[ChatMessage],
    include_history: bool,
) -> str:
    parts: list[str] = [
        f"当前角色：{role}",
    ]
    if include_history:
        history = _history_text(history_messages)
        if history:
            parts.append("历史对话（供上下文参考）：\n" + history)
    parts.append("用户请求：\n" + message.strip())
    return "\n\n".join(parts).strip()


@dataclass(frozen=True)
class PiChatResult:
    assistant: str
    events: list[dict[str, Any]]


class PiService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._deps_lock = asyncio.Lock()

    def _timeout_seconds(self) -> int:
        return max(10, int(self._settings.pi_timeout_seconds))

    def _resolve_backend(self) -> str:
        backend = (self._settings.pi_backend or "auto").strip().lower()
        if backend in {"local", "docker"}:
            return backend
        if shutil.which("docker"):
            return "docker"
        return "local"

    def _pi_mono_dir(self) -> Path:
        return self._settings.pi_mono_dir.expanduser().resolve()

    def _pi_agent_dir(self) -> Path:
        return self._settings.pi_agent_dir.expanduser().resolve()

    def _pi_runtime_dir(self) -> Path:
        return (self._pi_agent_dir().parent / "runtime").resolve()

    def _desired_coding_agent_version(self) -> str:
        """
        Prefer the vendored pi-mono version (if present), otherwise fall back to a pinned version.
        """

        mono = self._pi_mono_dir()
        pkg = mono / "packages" / "coding-agent" / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8"))
                ver = str((data or {}).get("version") or "").strip()
                if ver and _SEMVER_RE.match(ver):
                    return ver
            except Exception:
                pass
        # Keep a stable default for environments where pi-mono isn't vendored.
        return "0.54.0"

    def _build_models_json(self) -> dict[str, Any]:
        base_url = _normalize_openai_base_url(self._settings.openai_base_url)
        providers: dict[str, Any] = {}
        if base_url:
            providers["openai"] = {
                "baseUrl": base_url,
                "apiKey": "OPENAI_API_KEY",
                "authHeader": True,
            }
        return {"providers": providers}

    def _ensure_pi_agent_config(self) -> Path:
        agent_dir = self._pi_agent_dir()
        agent_dir.mkdir(parents=True, exist_ok=True)
        models_path = agent_dir / "models.json"
        models = self._build_models_json()
        # Write only if missing or changed, to avoid unnecessary churn.
        try:
            existing = json.loads(models_path.read_text(encoding="utf-8")) if models_path.exists() else None
        except Exception:
            existing = None
        if existing != models:
            models_path.write_text(json.dumps(models, ensure_ascii=False, indent=2), encoding="utf-8")
        return models_path

    def _tools_args(self, *, enable_shell: bool, enable_write: bool) -> list[str]:
        if not self._settings.pi_enable_tools:
            return ["--no-tools"]

        tools: list[str] = ["read", "grep", "find", "ls"]
        if enable_write:
            tools.extend(["edit", "write"])
        if enable_shell:
            tools.append("bash")
        return ["--tools", ",".join(dict.fromkeys(tools))]

    def _normalize_model(self, model: str | None) -> str:
        value = (model or self._settings.model or "gpt-5.2").strip()
        if not value:
            value = "gpt-5.2"
        if "/" in value:
            return value
        return f"openai/{value}"

    async def _ensure_deps(self, backend: str) -> None:
        runtime_dir = self._pi_runtime_dir()
        runtime_dir.mkdir(parents=True, exist_ok=True)
        version = self._desired_coding_agent_version()

        pkg_json_path = runtime_dir / "package.json"
        desired_pkg_json = {
            "name": "aistaff-pi-runtime",
            "private": True,
            "type": "module",
            "dependencies": {
                "@mariozechner/pi-coding-agent": version,
            },
        }

        # Write only if missing or changed (avoid churn).
        try:
            existing = json.loads(pkg_json_path.read_text(encoding="utf-8")) if pkg_json_path.exists() else None
        except Exception:
            existing = None
        if existing != desired_pkg_json:
            pkg_json_path.write_text(json.dumps(desired_pkg_json, ensure_ascii=False, indent=2), encoding="utf-8")

        async with self._deps_lock:
            if (runtime_dir / "node_modules").exists():
                return

            if backend == "docker":
                docker = shutil.which("docker")
                if not docker:
                    raise ValueError("docker not found; set AISTAFF_PI_BACKEND=local or install docker")

                args = [
                    docker,
                    "run",
                    "--rm",
                    "-e",
                    "HUSKY=0",
                    "-v",
                    f"{runtime_dir}:/pi-runtime",
                    "-w",
                    "/pi-runtime",
                    self._settings.pi_docker_image,
                    "npm",
                    "install",
                    "--no-audit",
                    "--no-fund",
                ]
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=self._timeout_seconds())
                except asyncio.TimeoutError as e:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    raise ValueError(f"pi deps install timed out after {self._timeout_seconds()}s") from e

                if proc.returncode != 0:
                    out = out_b.decode("utf-8", errors="ignore").strip()
                    err = err_b.decode("utf-8", errors="ignore").strip()
                    raise ValueError(f"pi deps install failed (exit={proc.returncode}): {_truncate(err or out or 'unknown error', 1200)}")
                return

            npm = shutil.which("npm")
            if not npm:
                raise ValueError("npm not found; set AISTAFF_PI_BACKEND=docker or install Node.js >= 20")
            env = os.environ.copy()
            env["HUSKY"] = "0"
            proc = await asyncio.create_subprocess_exec(
                npm,
                "install",
                "--no-audit",
                "--no-fund",
                cwd=str(runtime_dir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=self._timeout_seconds())
            except asyncio.TimeoutError as e:
                try:
                    proc.kill()
                except Exception:
                    pass
                raise ValueError(f"pi deps install timed out after {self._timeout_seconds()}s") from e
            if proc.returncode != 0:
                out = out_b.decode("utf-8", errors="ignore").strip()
                err = err_b.decode("utf-8", errors="ignore").strip()
                raise ValueError(f"pi deps install failed (exit={proc.returncode}): {_truncate(err or out or 'unknown error', 1200)}")

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
    ) -> PiChatResult:
        backend = self._resolve_backend()
        await self._ensure_deps(backend)
        self._ensure_pi_agent_config()

        workspace = workspace_root.resolve()
        used_model = self._normalize_model(model)

        runtime_dir = self._pi_runtime_dir()
        cli_path = runtime_dir / "node_modules" / "@mariozechner" / "pi-coding-agent" / "dist" / "cli.js"
        if not cli_path.exists():
            raise ValueError(f"Pi runtime is missing CLI. Expected: {cli_path}")

        user_prompt = _build_user_prompt(
            role=role,
            message=message,
            history_messages=session.messages,
            include_history=True,
        )

        events: list[dict[str, Any]] = [
            {
                "type": "pi_start",
                "backend": backend,
                "workspace": str(workspace),
                "model": used_model,
                "runtime_dir": str(runtime_dir),
                "coding_agent_version": self._desired_coding_agent_version(),
                "tools_enabled": bool(self._settings.pi_enable_tools),
                "tools_requested": {"shell": bool(enable_shell), "write": bool(enable_write)},
            }
        ]

        started_at = time.time()
        assistant = ""

        env = os.environ.copy()
        if self._settings.openai_api_key:
            env["OPENAI_API_KEY"] = self._settings.openai_api_key
        env["PI_CODING_AGENT_DIR"] = str(self._pi_agent_dir())
        env["NO_COLOR"] = "1"
        env["CI"] = "1"

        tool_args = self._tools_args(enable_shell=enable_shell, enable_write=enable_write)
        base_args: list[str] = [
            "--mode",
            "text",
            "--print",
            "--no-session",
            "--model",
            used_model,
            *tool_args,
        ]
        if system_prompt and system_prompt.strip():
            base_args.extend(["--append-system-prompt", system_prompt.strip()])

        if backend == "docker":
            docker = shutil.which("docker")
            if not docker:
                raise ValueError("docker not found; set AISTAFF_PI_BACKEND=local or install docker")

            # Mount workspace + runtime dir, while the process cwd stays in the mounted workspace.
            args = [
                docker,
                "run",
                "--rm",
                "-i",
                "-v",
                f"{runtime_dir}:/pi-runtime",
                "-v",
                f"{workspace}:/work",
                "-v",
                f"{self._pi_agent_dir()}:/pi-agent",
                "-w",
                "/work",
                "-e",
                f"OPENAI_API_KEY={env.get('OPENAI_API_KEY', '')}",
                "-e",
                "NO_COLOR=1",
                "-e",
                "CI=1",
                "-e",
                "PI_CODING_AGENT_DIR=/pi-agent",
                self._settings.pi_docker_image,
                "node",
                "/pi-runtime/node_modules/@mariozechner/pi-coding-agent/dist/cli.js",
                *base_args,
                user_prompt,
            ]
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            node = shutil.which("node")
            if not node:
                raise ValueError("node not found; set AISTAFF_PI_BACKEND=docker or install Node.js >= 20")

            args = [
                node,
                str(cli_path),
                *base_args,
                user_prompt,
            ]
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(workspace),
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
            raise ValueError(f"Pi timed out after {self._timeout_seconds()}s") from e

        stdout = stdout_b.decode("utf-8", errors="ignore").strip()
        stderr = stderr_b.decode("utf-8", errors="ignore").strip()

        if proc.returncode != 0:
            raise ValueError(f"Pi command failed (exit={proc.returncode}): {_truncate(stderr or stdout or 'unknown error', 1200)}")

        assistant = stdout.strip()
        if not assistant:
            assistant = "（Pi 未返回可显示的文本输出）"

        events.append(
            {
                "type": "pi_done",
                "elapsed_ms": int((time.time() - started_at) * 1000),
                "stdout_preview": _truncate(stdout, 1200),
                "stderr_preview": _truncate(stderr, 1200),
            }
        )
        return PiChatResult(assistant=assistant, events=events)
