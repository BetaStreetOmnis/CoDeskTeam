from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..config import Settings


_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_segment(value: str, fallback: str) -> str:
    cleaned = _SEGMENT_RE.sub("_", (value or "").strip())
    cleaned = cleaned.strip("._-")
    if not cleaned:
        return fallback
    return cleaned[:80]


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass(frozen=True)
class TaskArtifact:
    task_id: str
    task_dir: Path
    prompt_path: Path
    log_path: Path
    meta_path: Path
    assistant_path: Path
    location: str
    relative_dir: str | None

    def event_payload(self) -> dict[str, str | None]:
        return {
            "type": "task_artifact",
            "task_id": self.task_id,
            "location": self.location,
            "path": self.relative_dir,
        }


def _tasks_root_in_workspace(workspace_root: Path) -> Path:
    preferred = workspace_root / ".jetlinks-ai" / "tasks"
    legacy = workspace_root / ".aistaff" / "tasks"
    if (workspace_root / ".jetlinks-ai").exists():
        return preferred
    if (workspace_root / ".aistaff").exists():
        return legacy
    return preferred


def _tasks_root_in_data(settings: Settings) -> Path:
    return settings.db_path.parent / "tasks"


def _try_create_task_dir(base_root: Path, session_id: str, task_id: str) -> Path | None:
    safe_session = _safe_segment(session_id, "session")
    safe_task = _safe_segment(task_id, "task")
    target = base_root / f"session-{safe_session}" / safe_task
    try:
        target.mkdir(parents=True, exist_ok=True)
        return target
    except Exception:
        return None


def prepare_task_artifact(
    *,
    settings: Settings,
    workspace_root: Path,
    session_id: str,
) -> TaskArtifact | None:
    task_id = uuid4().hex
    workspace_root = workspace_root.resolve()

    base_dir = _try_create_task_dir(_tasks_root_in_workspace(workspace_root), session_id, task_id)
    location = "workspace"
    relative_dir: str | None = None
    if base_dir is None:
        base_dir = _try_create_task_dir(_tasks_root_in_data(settings), session_id, task_id)
        location = "data"

    if base_dir is None:
        return None

    try:
        if location == "workspace":
            relative_dir = str(base_dir.relative_to(workspace_root))
        else:
            relative_dir = str(base_dir.relative_to(settings.db_path.parent.resolve()))
    except Exception:
        relative_dir = None

    return TaskArtifact(
        task_id=task_id,
        task_dir=base_dir,
        prompt_path=base_dir / "prompt.txt",
        log_path=base_dir / "run.log",
        meta_path=base_dir / "meta.json",
        assistant_path=base_dir / "assistant.txt",
        location=location,
        relative_dir=relative_dir,
    )


def write_task_prompt(artifact: TaskArtifact, prompt: str) -> None:
    try:
        artifact.prompt_path.write_text(prompt, encoding="utf-8")
    except Exception:
        pass


def append_task_log(artifact: TaskArtifact, *, label: str, stdout: str, stderr: str) -> None:
    try:
        with artifact.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n--- {label} ---\n")
            if stdout:
                handle.write("\n[stdout]\n")
                handle.write(stdout)
                if not stdout.endswith("\n"):
                    handle.write("\n")
            if stderr:
                handle.write("\n[stderr]\n")
                handle.write(stderr)
                if not stderr.endswith("\n"):
                    handle.write("\n")
    except Exception:
        pass


def write_task_assistant(artifact: TaskArtifact, assistant: str) -> None:
    if not assistant:
        return
    try:
        artifact.assistant_path.write_text(assistant, encoding="utf-8")
    except Exception:
        pass


def write_task_meta(artifact: TaskArtifact, payload: dict) -> None:
    meta = {
        "schema": "aistaff.task.v1",
        "updated_at": _now_iso(),
        **payload,
    }
    try:
        with artifact.meta_path.open("w", encoding="utf-8") as handle:
            json.dump(meta, handle, ensure_ascii=True, indent=2)
    except Exception:
        pass


def task_base_meta(
    *,
    artifact: TaskArtifact,
    session_id: str,
    provider: str,
    model: str,
    workspace: Path,
    sandbox: str,
    dangerous_bypass: bool,
    enable_shell: bool,
    enable_write: bool,
    enable_browser: bool,
    resume_id: str | None,
    created_at: str | None = None,
) -> dict:
    return {
        "task_id": artifact.task_id,
        "session_id": session_id,
        "provider": provider,
        "model": model,
        "workspace": str(workspace),
        "sandbox": sandbox,
        "dangerous_bypass": bool(dangerous_bypass),
        "enable_shell": bool(enable_shell),
        "enable_write": bool(enable_write),
        "enable_browser": bool(enable_browser),
        "resume_id": resume_id,
        "task_dir": str(artifact.task_dir),
        "prompt_file": artifact.prompt_path.name,
        "log_file": artifact.log_path.name,
        "assistant_file": artifact.assistant_path.name,
        "location": artifact.location,
        "relative_dir": artifact.relative_dir,
        "created_at": created_at or _now_iso(),
    }
