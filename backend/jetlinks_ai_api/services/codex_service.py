from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..agent.types import ChatMessage
from ..config import Settings
from ..session_store import SessionState
from .task_artifact_service import (
    append_task_log,
    prepare_task_artifact,
    task_base_meta,
    write_task_assistant,
    write_task_meta,
    write_task_prompt,
)


_FILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_MAX_IMAGE_ATTACHMENTS = 4
_MAX_HISTORY_MESSAGES = 16


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 14)] + "\n…(truncated)"


def _safe_file_from_outputs(outputs_dir: Path, file_id: str) -> Path | None:
    fid = (file_id or "").strip()
    if not fid or ".." in fid or not _FILE_ID_RE.match(fid):
        return None
    base = outputs_dir.resolve()
    full = (base / fid).resolve()
    if full == base or not str(full).startswith(str(base) + os.sep):
        return None
    if not full.exists() or not full.is_file():
        return None
    return full


def _is_image_attachment(att: dict[str, Any]) -> bool:
    kind = str(att.get("kind") or att.get("type") or "").strip().lower()
    if kind == "image":
        return True
    ctype = str(att.get("content_type") or "").strip().lower()
    if ctype.startswith("image/"):
        return True
    fid = str(att.get("file_id") or "").strip().lower()
    return Path(fid).suffix.lower() in _IMAGE_EXTS


def _normalize_reasoning_effort(value: str | None) -> str:
    effort = (value or "").strip().lower()
    if effort in {"low", "medium", "high"}:
        return effort
    return "medium"


def _parse_json_error_message(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    try:
        obj = json.loads(text)
    except Exception:
        return text
    if isinstance(obj, dict):
        err = obj.get("error")
        if isinstance(err, dict):
            msg = str(err.get("message") or "").strip()
            if msg:
                return msg
    return text


def _is_noisy_codex_stderr_line(line: str) -> bool:
    t = (line or "").strip()
    if not t:
        return True
    return "state db missing rollout path for thread" in t


def _history_text(messages: list[ChatMessage]) -> str:
    lines: list[str] = []
    history = [m for m in messages if m.role in {"user", "assistant"}][- _MAX_HISTORY_MESSAGES :]
    for m in history:
        role = "用户" if m.role == "user" else "助手"
        content = (m.content or "").strip()
        if not content:
            continue
        lines.append(f"{role}：{_truncate(content, 2000)}")
    return "\n\n".join(lines).strip()


def _build_prompt(
    *,
    role: str,
    message: str,
    system_prompt: str | None,
    history_messages: list[ChatMessage],
    attachment_hints: list[str],
    include_history: bool,
) -> str:
    parts: list[str] = [
        "你正在 JetLinks AI 中作为 Codex 执行任务。",
        f"当前角色：{role}。",
        "请直接给出结果；如需要修改代码，请明确说明改动点与验证方式。",
    ]

    extra = (system_prompt or "").strip()
    if extra:
        parts.append(f"附加系统约束（必须遵守）：\n{extra}")

    if include_history:
        history = _history_text(history_messages)
        if history:
            parts.append(f"历史对话（供上下文参考）：\n{history}")

    if attachment_hints:
        parts.append("用户附带文件（可按需读取）：\n" + "\n".join(attachment_hints))

    parts.append(f"当前用户请求：\n{message.strip()}")
    return "\n\n".join(parts).strip()


@dataclass(frozen=True)
class CodexChatResult:
    assistant: str
    events: list[dict[str, Any]]


class CodexService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _resolve_command(self) -> list[str]:
        raw = (self._settings.codex_command or "codex").strip()
        parts = shlex.split(raw) if raw else ["codex"]
        if not parts:
            parts = ["codex"]

        cmd0 = parts[0]
        if "/" in cmd0 or "\\" in cmd0:
            p = Path(cmd0).expanduser()
            if not p.exists():
                raise ValueError(f"Codex command not found: {p}")
            parts[0] = str(p)
            return parts

        resolved = shutil.which(cmd0)
        if not resolved:
            raise ValueError(
                "Codex CLI not found. Please install it first: https://github.com/openai/codex "
                "or set JETLINKS_AI_CODEX_CMD to an executable path."
            )
        parts[0] = resolved
        return parts

    def _timeout_seconds(self) -> int:
        return max(10, int(self._settings.codex_timeout_seconds))

    def _is_missing_session_error(self, message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return False
        if "session" not in text:
            return False
        missing_hints = ("not found", "no sessions", "no session", "could not find", "missing session")
        return any(hint in text for hint in missing_hints)

    def _collect_attachments(
        self,
        *,
        attachments: list[dict[str, Any]] | None,
        outputs_dir: Path,
    ) -> tuple[list[Path], list[str]]:
        image_paths: list[Path] = []
        image_set: set[str] = set()
        hints: list[str] = []

        for att in attachments or []:
            if not isinstance(att, dict):
                continue
            file_id = str(att.get("file_id") or "").strip()
            if not file_id:
                continue
            filename = str(att.get("filename") or file_id).strip() or file_id
            kind = "image" if _is_image_attachment(att) else "file"

            full_path = _safe_file_from_outputs(outputs_dir, file_id)
            if full_path is not None:
                hints.append(f"- {filename}（{kind}）：{full_path}")
                if kind == "image" and len(image_paths) < _MAX_IMAGE_ATTACHMENTS:
                    ext = full_path.suffix.lower()
                    key = str(full_path)
                    if ext in _IMAGE_EXTS and key not in image_set:
                        image_paths.append(full_path)
                        image_set.add(key)
            else:
                hints.append(f"- {filename}（{kind}）：file_id={file_id}")

        return image_paths, hints

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
        enable_browser: bool,
        dangerous_bypass: bool,
        system_prompt: str | None,
        attachments: list[dict[str, Any]] | None,
    ) -> CodexChatResult:
        cmd = self._resolve_command()
        workspace = workspace_root.resolve()
        outputs_dir = self._settings.outputs_dir.resolve()
        script_path = (self._settings.app_root / "scripts" / "aistaff_skill_runner.py").resolve()
        script_dir = script_path.parent
        allow_write = bool(enable_shell) or bool(enable_write)
        sandbox = "workspace-write" if allow_write else "read-only"
        used_model = (model or self._settings.model or "gpt-5.2-codex").strip() or "gpt-5.2-codex"
        reasoning_effort = _normalize_reasoning_effort(self._settings.codex_reasoning_effort)

        image_paths, attachment_hints = self._collect_attachments(attachments=attachments, outputs_dir=outputs_dir)
        resume_id = session.codex_thread_id
        created_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        artifact = prepare_task_artifact(
            settings=self._settings,
            workspace_root=workspace,
            session_id=session.session_id,
        )
        artifact_event = artifact.event_payload() if artifact else None
        artifact_notes: list[str] = []
        attempts = 0
        final_resume_id: str | None = resume_id
        final_thread_id: str | None = None

        def build_prompt(include_history: bool) -> str:
            return _build_prompt(
                role=role,
                message=message,
                system_prompt=system_prompt,
                history_messages=session.messages,
                attachment_hints=attachment_hints,
                include_history=include_history,
            )

        prompt = build_prompt(resume_id is None)

        def build_args(next_resume_id: str | None) -> list[str]:
            base: list[str] = [*cmd, "exec"]
            if next_resume_id:
                base.append("resume")
            if dangerous_bypass:
                base.append("--dangerously-bypass-approvals-and-sandbox")

            base.extend(
                [
                    "--json",
                    "--skip-git-repo-check",
                    "--color",
                    "never",
                    "--sandbox",
                    sandbox,
                    "-c",
                    f'model_reasoning_effort=\"{reasoning_effort}\"',
                    "--model",
                    used_model,
                    "-C",
                    str(workspace),
                ]
            )

            if allow_write:
                base.append("--full-auto")

            # If outputs dir is outside workspace, explicitly allow Codex to access it.
            try:
                _ = outputs_dir.relative_to(workspace)
            except Exception:
                base.extend(["--add-dir", str(outputs_dir)])

            if script_path.exists():
                try:
                    _ = script_dir.relative_to(workspace)
                except Exception:
                    base.extend(["--add-dir", str(script_dir)])

            for p in image_paths:
                base.extend(["-i", str(p)])

            if next_resume_id:
                base.append(next_resume_id)

            return base

        async def run_with_args(
            args: list[str],
            prompt_text: str,
            attempt_label: str,
        ) -> tuple[str, list[dict[str, Any]], str | None, dict[str, Any] | None]:
            if artifact:
                write_task_prompt(artifact, prompt_text)

            events: list[dict[str, Any]] = []
            if artifact_event:
                events.append(artifact_event)
            events.append(
                {
                    "type": "codex_start",
                    "workspace": str(workspace),
                    "model": used_model,
                    "sandbox": sandbox,
                    "images_attached": len(image_paths),
                    "reasoning_effort": reasoning_effort,
                    "resume_id": args[-1] if resume_id and args[-1] == resume_id else None,
                    "dangerous_bypass": dangerous_bypass,
                }
            )

            started_at = time.time()
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(workspace),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy(),
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(prompt_text.encode("utf-8")),
                    timeout=self._timeout_seconds(),
                )
            except asyncio.TimeoutError as e:
                try:
                    proc.kill()
                except Exception:
                    pass
                raise ValueError(f"Codex timed out after {self._timeout_seconds()}s") from e

            stdout = stdout_b.decode("utf-8", errors="ignore")
            stderr = stderr_b.decode("utf-8", errors="ignore")
            if artifact:
                append_task_log(artifact, label=attempt_label, stdout=stdout, stderr=stderr)

            thread_id = ""
            usage: dict[str, Any] | None = None
            assistant = ""
            reasoning_fallback = ""
            turn_failed_msg = ""

            for raw in stdout.splitlines():
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue

                et = str(obj.get("type") or "").strip()
                if et == "thread.started":
                    thread_id = str(obj.get("thread_id") or "").strip()
                    continue
                if et == "turn.completed":
                    usage_obj = obj.get("usage")
                    if isinstance(usage_obj, dict):
                        usage = usage_obj
                    continue
                if et == "turn.failed":
                    err = obj.get("error")
                    if isinstance(err, dict):
                        turn_failed_msg = _parse_json_error_message(str(err.get("message") or ""))
                    else:
                        turn_failed_msg = _parse_json_error_message(str(err or ""))
                    continue
                if et == "error":
                    turn_failed_msg = _parse_json_error_message(str(obj.get("message") or ""))
                    continue
                if et != "item.completed":
                    continue

                item = obj.get("item")
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").strip()
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                if item_type == "agent_message":
                    assistant = text
                elif item_type == "reasoning":
                    reasoning_fallback = text

            stderr_lines = [line.strip() for line in stderr.splitlines() if line.strip()]
            filtered_stderr = [line for line in stderr_lines if not _is_noisy_codex_stderr_line(line)]
            if filtered_stderr:
                events.append({"type": "codex_warning", "message": _truncate("\n".join(filtered_stderr[:3]), 1200)})

            if proc.returncode != 0:
                msg = turn_failed_msg or _truncate("\n".join(filtered_stderr) or "unknown error", 1200)
                raise ValueError(f"Codex command failed (exit={proc.returncode}): {msg}")

            if turn_failed_msg:
                raise ValueError(f"Codex request failed: {turn_failed_msg}")

            if not assistant:
                assistant = reasoning_fallback or "（Codex 未返回可显示的文本输出）"

            events.append(
                {
                    "type": "codex_done",
                    "thread_id": thread_id or None,
                    "elapsed_ms": int((time.time() - started_at) * 1000),
                    "usage": usage or {},
                }
            )
            return assistant, events, thread_id or None, usage

        args = build_args(resume_id)
        try:
            attempts += 1
            final_resume_id = resume_id
            assistant, events, thread_id, _usage = await run_with_args(args, prompt, f"attempt-{attempts}")
        except ValueError as e:
            if resume_id and self._is_missing_session_error(str(e)):
                session.codex_thread_id = None
                artifact_notes.append("resume_missing_session")
                retry_args = build_args(None)
                retry_prompt = build_prompt(True)
                attempts += 1
                final_resume_id = None
                assistant, events, thread_id, _usage = await run_with_args(retry_args, retry_prompt, f"attempt-{attempts}")
                events.insert(1, {"type": "codex_warning", "message": "Codex 会话不存在，已自动开启新会话。"})
            else:
                if artifact:
                    write_task_meta(
                        artifact,
                        {
                            **task_base_meta(
                                artifact=artifact,
                                session_id=session.session_id,
                                provider="codex",
                                model=used_model,
                                workspace=workspace,
                                sandbox=sandbox,
                                dangerous_bypass=dangerous_bypass,
                                enable_shell=enable_shell,
                                enable_write=enable_write,
                                enable_browser=enable_browser,
                                resume_id=final_resume_id,
                                created_at=created_at,
                            ),
                            "status": "failed",
                            "error": str(e),
                            "attempts": attempts,
                            "notes": artifact_notes,
                            "finished_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                        },
                    )
                raise
        except Exception as e:
            if artifact:
                write_task_meta(
                    artifact,
                    {
                        **task_base_meta(
                            artifact=artifact,
                            session_id=session.session_id,
                            provider="codex",
                            model=used_model,
                            workspace=workspace,
                            sandbox=sandbox,
                            dangerous_bypass=dangerous_bypass,
                            enable_shell=enable_shell,
                            enable_write=enable_write,
                            enable_browser=enable_browser,
                            resume_id=final_resume_id,
                            created_at=created_at,
                        ),
                        "status": "failed",
                        "error": str(e),
                        "attempts": attempts,
                        "notes": artifact_notes,
                        "finished_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                    },
                )
            raise

        if thread_id:
            session.codex_thread_id = thread_id
        final_thread_id = thread_id or None

        if artifact:
            write_task_assistant(artifact, assistant)
            write_task_meta(
                artifact,
                {
                    **task_base_meta(
                        artifact=artifact,
                        session_id=session.session_id,
                        provider="codex",
                        model=used_model,
                        workspace=workspace,
                        sandbox=sandbox,
                        dangerous_bypass=dangerous_bypass,
                        enable_shell=enable_shell,
                        enable_write=enable_write,
                        enable_browser=enable_browser,
                        resume_id=final_resume_id,
                        created_at=created_at,
                    ),
                    "status": "success",
                    "thread_id": final_thread_id,
                    "attempts": attempts,
                    "notes": artifact_notes,
                    "finished_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                },
            )

        return CodexChatResult(assistant=assistant, events=events)
