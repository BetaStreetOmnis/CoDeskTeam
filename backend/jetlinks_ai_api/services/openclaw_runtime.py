from __future__ import annotations

import asyncio
import shlex
import shutil
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from ..config import Settings


def _resolve_binary_command(raw: str) -> list[str]:
    value = (raw or "").strip() or "openclaw"
    parts = shlex.split(value)
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
        raise ValueError("OpenClaw CLI not found. Please install it or set JETLINKS_AI_OPENCLAW_CMD.")
    parts[0] = resolved
    return parts


@dataclass
class OpenClawRuntime:
    settings: Settings
    _proc: asyncio.subprocess.Process | None = None
    _stdout_task: asyncio.Task | None = None
    _stderr_task: asyncio.Task | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def _drain(self, stream: asyncio.StreamReader | None, label: str) -> None:
        if stream is None:
            return
        while True:
            try:
                line = await stream.readline()
            except Exception:
                return
            if not line:
                return
            text = line.decode("utf-8", errors="ignore").strip()
            if not text:
                continue
            if "openclaw" in text.lower() or "gateway" in text.lower():
                print(f"[jetlinks-ai][openclaw:{label}] {text}")

    def _gateway_command(self) -> list[str]:
        explicit = (self.settings.openclaw_gateway_command or "").strip()
        if explicit:
            return _resolve_binary_command(explicit)
        base = _resolve_binary_command(self.settings.openclaw_command)
        return [
            *base,
            "gateway",
            "--port",
            str(max(1, int(self.settings.openclaw_gateway_port))),
            "--bind",
            (self.settings.openclaw_gateway_bind or "loopback").strip() or "loopback",
        ]

    async def start(self) -> None:
        if not bool(self.settings.openclaw_enabled) or not bool(self.settings.openclaw_embedded):
            return
        async with self._lock:
            if self._proc and self._proc.returncode is None:
                return

            cmd = self._gateway_command()
            workdir = self.settings.openclaw_working_dir
            cwd = str(workdir) if workdir.exists() else str(self.settings.app_root)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._proc = proc
            self._stdout_task = asyncio.create_task(self._drain(proc.stdout, "out"))
            self._stderr_task = asyncio.create_task(self._drain(proc.stderr, "err"))
            print(f"[jetlinks-ai] OpenClaw embedded runtime started (pid={proc.pid})")

    async def stop(self) -> None:
        async with self._lock:
            proc = self._proc
            if not proc:
                return
            if proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            self._proc = None
            for t in (self._stdout_task, self._stderr_task):
                if t:
                    t.cancel()
            self._stdout_task = None
            self._stderr_task = None


_RUNTIME: OpenClawRuntime | None = None


def get_openclaw_runtime(settings: Settings) -> OpenClawRuntime:
    global _RUNTIME
    if _RUNTIME is None or _RUNTIME.settings is not settings:
        _RUNTIME = OpenClawRuntime(settings=settings)
    return _RUNTIME
