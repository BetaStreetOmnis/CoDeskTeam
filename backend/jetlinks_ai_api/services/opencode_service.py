from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings
from ..session_store import SessionState


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 14)] + "\n…(truncated)"


def _summarize_opencode_error(info: dict[str, Any]) -> str | None:
    err = info.get("error")
    if not err:
        return None
    if isinstance(err, str):
        msg = err.strip()
        return msg or None
    if not isinstance(err, dict):
        try:
            return str(err)
        except Exception:
            return None

    name = str(err.get("name") or "").strip()
    data = err.get("data") if isinstance(err.get("data"), dict) else {}
    status = data.get("statusCode")
    msg = data.get("message") or data.get("responseBody") or err.get("message")
    msg_str = str(msg or "").strip()
    prefix = f"{name}: " if name else ""
    if isinstance(status, int):
        prefix = f"{prefix}(status {status}) "
    out = (prefix + msg_str).strip()
    return out or None


def _is_sensitive_env_path(path: str) -> bool:
    # deny common secret files; allow templates
    base = Path(path).name.lower()
    if base in {".env.example", ".env.sample", ".env.template"}:
        return False
    return base == ".env" or base.startswith(".env.")


def _resolve_under_workspace(workspace: Path, path: str) -> Path | None:
    try:
        p = Path(path)
    except Exception:
        return None

    candidate = p if p.is_absolute() else (workspace / p)
    try:
        resolved = candidate.resolve()
    except Exception:
        return None

    base = workspace.resolve()
    if resolved == base or not str(resolved).startswith(str(base) + os.sep):
        return None
    return resolved


def _is_sensitive_workspace_path(workspace: Path, path: str) -> bool:
    resolved = _resolve_under_workspace(workspace, path)
    if not resolved:
        return False

    if _is_sensitive_env_path(str(resolved)):
        return True

    try:
        rel = resolved.relative_to(workspace.resolve())
    except Exception:
        return True

    parts = {p.lower() for p in rel.parts}
    return bool({".aistaff", ".jetlinks-ai"}.intersection(parts))


def _parse_model_string(model: str | None) -> dict[str, str] | None:
    value = (model or "").strip()
    if not value:
        return None
    if "/" in value:
        provider_id, model_id = value.split("/", 1)
        provider_id = provider_id.strip()
        model_id = model_id.strip()
        if provider_id and model_id:
            return {"providerID": provider_id, "modelID": model_id}
    return {"providerID": "openai", "modelID": value}


@dataclass(frozen=True)
class OpencodeChatResult:
    assistant: str
    events: list[dict[str, Any]]


class OpencodeService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _auth(self) -> tuple[str, str] | None:
        pwd = (self._settings.opencode_password or "").strip()
        if not pwd:
            return None
        return (self._settings.opencode_username, pwd)

    def _headers(self, workspace_root: Path) -> dict[str, str]:
        # opencode server picks directory via query "directory" or header "x-opencode-directory"
        return {"x-opencode-directory": str(workspace_root)}

    def _timeout(self) -> httpx.Timeout:
        t = max(1, int(self._settings.opencode_timeout_seconds))
        return httpx.Timeout(t)

    async def _ensure_session(self, client: httpx.AsyncClient, st: SessionState) -> str:
        if st.opencode_session_id:
            return st.opencode_session_id

        try:
            res = await client.post("/session", json={"title": "jetlinks-ai"})
        except httpx.RequestError as e:  # pragma: no cover
            raise ValueError(
                f"OpenCode server unreachable at {self._settings.opencode_base_url}. "
                "Please start it: `opencode serve --hostname 127.0.0.1 --port 4096`"
            ) from e

        if res.status_code >= 400:
            raise ValueError(f"OpenCode server error {res.status_code}: {res.text}")
        data = res.json()
        sid = str((data or {}).get("id") or "").strip()
        if not sid:
            raise ValueError("OpenCode server returned invalid session response (missing id)")
        st.opencode_session_id = sid
        return sid

    async def _list_permissions(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        res = await client.get("/permission")
        if res.status_code >= 400:
            return []
        data = res.json()
        return data if isinstance(data, list) else []

    async def _reply_permission(self, client: httpx.AsyncClient, request_id: str, reply: str, message: str | None) -> None:
        payload: dict[str, Any] = {"reply": reply}
        if message:
            payload["message"] = message
        await client.post(f"/permission/{request_id}/reply", json=payload)

    async def _auto_handle_permissions(
        self,
        client: httpx.AsyncClient,
        *,
        session_id: str,
        workspace_root: Path,
        enable_shell: bool,
        enable_write: bool,
        stop: asyncio.Event,
        events: list[dict[str, Any]],
    ) -> None:
        workspace = workspace_root.resolve()

        while not stop.is_set():
            try:
                pending = await self._list_permissions(client)
            except Exception:
                await asyncio.sleep(0.25)
                continue

            for req in pending:
                try:
                    if str(req.get("sessionID") or "") != session_id:
                        continue
                    req_id = str(req.get("id") or "")
                    perm = str(req.get("permission") or "")
                    patterns = req.get("patterns") or []

                    reply = "once"
                    msg: str | None = None

                    if perm == "edit":
                        if not enable_write:
                            reply = "reject"
                            msg = "jetlinks-ai: edit disabled"
                        elif any(isinstance(p, str) and _is_sensitive_workspace_path(workspace, p) for p in patterns):
                            reply = "reject"
                            msg = "jetlinks-ai: editing sensitive files disabled"
                    elif perm == "bash" and not enable_shell:
                        reply = "reject"
                        msg = "jetlinks-ai: bash disabled"
                    elif perm == "external_directory":
                        reply = "reject"
                        msg = "jetlinks-ai: external directory access disabled"
                    elif perm == "read":
                        # Reject sensitive env/data files; allow within workspace.
                        if any(isinstance(p, str) and (_is_sensitive_workspace_path(workspace, p) or _is_sensitive_env_path(p)) for p in patterns):
                            reply = "reject"
                            msg = "jetlinks-ai: reading sensitive files disabled"
                        else:
                            for p in patterns:
                                if not isinstance(p, str):
                                    continue
                                resolved = _resolve_under_workspace(workspace, p)
                                if not resolved:
                                    reply = "reject"
                                    msg = "jetlinks-ai: read outside workspace disabled"
                                    break

                    events.append({"type": "opencode_permission", "permission": perm, "reply": reply, "patterns": patterns})
                    await self._reply_permission(client, req_id, reply, msg)
                except Exception:
                    continue

            await asyncio.sleep(0.25)

    def _extract_text(self, msg: dict[str, Any]) -> str:
        parts = msg.get("parts") or []
        if not isinstance(parts, list):
            return ""
        texts: list[str] = []
        for p in parts:
            if not isinstance(p, dict):
                continue
            if p.get("type") != "text":
                continue
            if p.get("synthetic"):
                continue
            t = str(p.get("text") or "").strip()
            if t:
                texts.append(t)
        return "\n\n".join(texts).strip()

    def _summarize_parts(self, msg: dict[str, Any]) -> list[dict[str, Any]]:
        parts = msg.get("parts") or []
        if not isinstance(parts, list):
            return []

        out: list[dict[str, Any]] = []
        for p in parts:
            if not isinstance(p, dict):
                continue
            t = str(p.get("type") or "")
            if t == "text":
                out.append({"type": "text", "text": _truncate(str(p.get("text") or ""), 800)})
            elif t == "tool":
                state = p.get("state") or {}
                out.append(
                    {
                        "type": "tool",
                        "tool": p.get("tool"),
                        "status": (state.get("status") if isinstance(state, dict) else None),
                        "error": (state.get("error") if isinstance(state, dict) else None),
                    }
                )
            elif t == "patch":
                out.append({"type": "patch", "files": p.get("files"), "hash": p.get("hash")})
            elif t == "file":
                out.append({"type": "file", "filename": p.get("filename"), "mime": p.get("mime")})
            else:
                out.append({"type": t})
        return out

    async def chat(
        self,
        *,
        session: SessionState,
        message: str,
        agent: str,
        model: str | None,
        workspace_root: Path,
        enable_shell: bool,
        enable_write: bool,
        system_prompt: str | None,
    ) -> OpencodeChatResult:
        # Enforce JetLinks AI toggles via opencode "tools" overrides.
        # (OpenCode maps this to permission rules: allow/deny pattern "*")
        tools: dict[str, bool] = {
            "edit": bool(enable_write),
            "bash": bool(enable_shell),
            "external_directory": False,
        }

        events: list[dict[str, Any]] = [
            {
                "type": "opencode_start",
                "base_url": self._settings.opencode_base_url,
                "workspace": str(workspace_root),
                "agent": agent,
                "model": model,
                "tools": tools,
            }
        ]

        async with httpx.AsyncClient(
            base_url=self._settings.opencode_base_url,
            headers=self._headers(workspace_root),
            auth=self._auth(),
            timeout=self._timeout(),
        ) as client:
            opencode_session_id = await self._ensure_session(client, session)

            stop = asyncio.Event()
            perm_task = asyncio.create_task(
                self._auto_handle_permissions(
                    client,
                    session_id=opencode_session_id,
                    workspace_root=workspace_root,
                    enable_shell=enable_shell,
                    enable_write=enable_write,
                    stop=stop,
                    events=events,
                )
            )

            started_at = time.time()
            try:
                effective_system = (system_prompt or "").strip() or "You are a helpful assistant."
                payload: dict[str, Any] = {
                    "agent": agent,
                    "parts": [{"type": "text", "text": message}],
                    "tools": tools,
                }
                parsed_model = _parse_model_string(model)
                if parsed_model:
                    payload["model"] = parsed_model
                # Some OpenAI-compatible gateways (e.g. tabcode) require non-empty instructions.
                # OpenCode maps `system` to the underlying model instructions/system prompt.
                payload["system"] = effective_system

                res = await client.post(f"/session/{opencode_session_id}/message", json=payload)
                if res.status_code >= 400:
                    raise ValueError(f"OpenCode error {res.status_code}: {res.text}")

                data = res.json()
                if not isinstance(data, dict):
                    raise ValueError("OpenCode returned invalid response")

                info = data.get("info") if isinstance(data.get("info"), dict) else {}
                assistant = self._extract_text(data).strip()
                if not assistant:
                    err = _summarize_opencode_error(info)
                    if err:
                        assistant = f"（OpenCode 请求失败：{_truncate(err, 600)}）"
                    else:
                        assistant = "（OpenCode 未返回可显示的文本输出）"
                events.append({"type": "opencode_info", "info": info})
                events.append({"type": "opencode_parts", "parts": self._summarize_parts(data)})
                events.append({"type": "opencode_done", "elapsed_ms": int((time.time() - started_at) * 1000)})
                return OpencodeChatResult(assistant=assistant, events=events)
            finally:
                stop.set()
                try:
                    await asyncio.wait_for(perm_task, timeout=2.0)
                except Exception:
                    perm_task.cancel()
