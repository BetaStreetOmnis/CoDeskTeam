from __future__ import annotations

import asyncio
import json
import shlex
import shutil
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings


def _try_json_load(text: str) -> dict[str, Any] | list[Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    for ln in reversed(lines):
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if isinstance(obj, (dict, list)):
            return obj
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    if isinstance(obj, (dict, list)):
        return obj
    return None


class OpenClawAdminService:
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
            raise ValueError("OpenClaw CLI not found")
        parts[0] = resolved
        return parts

    async def _run_json(self, args: list[str]) -> dict[str, Any] | list[Any] | None:
        cmd = self._resolve_command()
        workdir = self._settings.openclaw_working_dir
        cwd = str(workdir) if workdir.exists() else str(self._settings.app_root)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timeout = max(6, int(self._settings.openclaw_timeout_seconds))
        try:
            stdout_b, _stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return None
        if proc.returncode != 0:
            return None
        stdout = stdout_b.decode("utf-8", errors="ignore")
        return _try_json_load(stdout)

    async def probe_gateway(self) -> dict[str, Any]:
        base = str(self._settings.openclaw_gateway_base_url or "").strip().rstrip("/")
        out: dict[str, Any] = {"reachable": False, "base_url": base, "http_probe": None}
        if not base:
            return out

        urls = [f"{base}/health", f"{base}/status", base]
        try:
            async with httpx.AsyncClient(timeout=2.5) as client:
                for url in urls:
                    try:
                        resp = await client.get(url)
                    except Exception:
                        continue
                    if resp.status_code >= 500:
                        continue
                    body_text = (resp.text or "").strip()
                    body_json: dict[str, Any] | list[Any] | None = None
                    try:
                        body_json = resp.json()
                    except Exception:
                        body_json = None
                    out["reachable"] = True
                    out["http_probe"] = {
                        "url": url,
                        "status_code": int(resp.status_code),
                        "json": body_json if isinstance(body_json, (dict, list)) else None,
                        "text": body_text[:400] if body_text else None,
                    }
                    return out
        except Exception:
            return out
        return out

    async def gateway_status(self) -> dict[str, Any]:
        cli_ok = False
        cli_path = None
        try:
            cmd = self._resolve_command()
            cli_ok = True
            cli_path = cmd[0]
        except Exception:
            cli_ok = False
            cli_path = None

        gateway_json = await self._run_json(["gateway", "status", "--json"]) if cli_ok else None
        health_json = await self._run_json(["health", "--json"]) if cli_ok else None
        probe = await self.probe_gateway()
        return {
            "enabled": bool(self._settings.openclaw_enabled),
            "embedded": bool(self._settings.openclaw_embedded),
            "cli_available": cli_ok,
            "cli_path": cli_path,
            "gateway_base_url": str(self._settings.openclaw_gateway_base_url or "").strip().rstrip("/"),
            "gateway_port": int(self._settings.openclaw_gateway_port),
            "gateway_bind": str(self._settings.openclaw_gateway_bind or "loopback"),
            "workdir": str(self._settings.openclaw_working_dir),
            "gateway_status_json": gateway_json,
            "health_json": health_json,
            "probe": probe,
        }

    async def discover_plugins(self) -> list[dict[str, Any]]:
        raw = await self._run_json(["plugins", "list", "--json"])
        if raw is None:
            return []
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            items = raw.get("plugins") if isinstance(raw.get("plugins"), list) else raw.get("items")
            if not isinstance(items, list):
                items = []
        else:
            items = []

        out: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("id") or item.get("key") or item.get("name") or "").strip()
            if not key:
                continue
            out.append(
                {
                    "plugin_key": key,
                    "name": str(item.get("name") or key).strip() or key,
                    "version": str(item.get("version") or "").strip(),
                    "source": str(item.get("source") or item.get("path") or "").strip(),
                    "enabled": bool(item.get("enabled", True)),
                    "meta": item,
                }
            )
        return out

    async def discover_channels(self) -> list[dict[str, Any]]:
        raw = await self._run_json(["config", "get", "channels", "--json"])
        if not isinstance(raw, dict):
            return []

        channels_obj = raw.get("channels") if isinstance(raw.get("channels"), dict) else raw
        if not isinstance(channels_obj, dict):
            return []

        out: list[dict[str, Any]] = []
        for channel_key, cfg in channels_obj.items():
            key = str(channel_key or "").strip()
            if not key:
                continue
            cfg_obj = cfg if isinstance(cfg, dict) else {}
            out.append(
                {
                    "channel_key": key,
                    "channel_type": str(cfg_obj.get("type") or key).strip() or key,
                    "external_id": "",
                    "name": str(cfg_obj.get("label") or cfg_obj.get("name") or key).strip() or key,
                    "enabled": bool(cfg_obj.get("enabled", True)),
                    "meta": cfg_obj,
                }
            )
        return out

