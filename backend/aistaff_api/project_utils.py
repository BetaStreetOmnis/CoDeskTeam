from __future__ import annotations

import re
from pathlib import Path

from .config import Settings


def slugify(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", (value or "").strip().lower())
    cleaned = cleaned.strip("-._")
    return cleaned or fallback


def path_under_any_root(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            _ = path.relative_to(root)
            return True
        except Exception:
            continue
    return False


def resolve_project_path(settings: Settings, input_path: str) -> Path:
    raw = (input_path or "").strip()
    if not raw:
        raise ValueError("path 不能为空")

    p = Path(raw).expanduser()
    roots = list(settings.projects_roots or [])
    if not roots:
        roots = [settings.workspace_root]

    if not p.is_absolute():
        p = roots[0] / p

    try:
        resolved = p.resolve()
    except Exception:
        raise ValueError("path 无法解析") from None

    resolved_roots: list[Path] = []
    for r in roots:
        try:
            resolved_roots.append(Path(r).expanduser().resolve())
        except Exception:
            continue
    if not resolved_roots:
        resolved_roots = [settings.workspace_root.resolve()]

    if not path_under_any_root(resolved, resolved_roots):
        raise ValueError(f"项目路径不在允许范围（AISTAFF_PROJECTS_ROOT）：{resolved}")
    if not resolved.exists():
        raise ValueError(f"项目路径不存在：{resolved}")
    if not resolved.is_dir():
        raise ValueError(f"项目路径不是目录：{resolved}")
    if ".aistaff" in {part.lower() for part in resolved.parts}:
        raise ValueError("项目路径不能位于 .aistaff 目录内")
    return resolved


def resolve_user_workspace_root(
    settings: Settings,
    base_path: Path,
    team_id: int,
    user_id: int,
    team_name: str | None = None,
    user_name: str | None = None,
) -> Path:
    layout = (settings.workspace_layout or "shared").strip().lower()
    if layout != "per_user":
        return base_path

    user_dir = (settings.workspace_user_dir or "users").strip().strip("/\\")
    if not user_dir or ".." in user_dir:
        user_dir = "users"

    base_root = base_path.expanduser().resolve()
    team_segment = slugify(team_name or "", f"team-{int(team_id)}")
    user_segment = slugify(user_name or "", f"user-{int(user_id)}")
    target = (base_root / user_dir / team_segment / user_segment).resolve()
    try:
        _ = target.relative_to(base_root)
    except Exception:
        raise ValueError("用户工作区路径非法") from None

    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception:
        raise ValueError("无法创建用户工作区目录") from None

    return target
