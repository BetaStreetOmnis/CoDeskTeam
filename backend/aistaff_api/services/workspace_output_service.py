from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import Settings
from ..db import utc_now_iso
from ..project_utils import slugify


def _ensure_outputs_dir(workspace_root: Path) -> Path:
    root = workspace_root.resolve()
    outputs_dir = (root / "outputs").resolve()
    try:
        _ = outputs_dir.relative_to(root)
    except Exception:
        raise ValueError("工作区输出目录非法") from None
    outputs_dir.mkdir(parents=True, exist_ok=True)
    return outputs_dir


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for i in range(2, 50):
        candidate = path.with_name(f"{stem}-{i}{suffix}")
        if not candidate.exists():
            return candidate
    return path


def save_output_to_workspace(
    *,
    settings: Settings,
    workspace_root: Path,
    file_id: str,
    title: str | None,
    kind: str,
    payload: dict[str, Any] | None,
    meta: dict[str, Any] | None,
    source: str,
) -> dict[str, str]:
    outputs_dir = _ensure_outputs_dir(workspace_root)
    src = (settings.outputs_dir / file_id).resolve()
    if not src.exists() or not src.is_file():
        return {}

    safe_title = slugify(title or kind or "output", "output")[:60]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    short_id = Path(file_id).stem[:8] if file_id else "file"
    base = f"{safe_title}-{stamp}-{short_id}"
    dest = _unique_path(outputs_dir / f"{base}{src.suffix}")

    shutil.copy2(src, dest)

    context = {
        "kind": kind,
        "title": title or "",
        "source": source,
        "created_at": utc_now_iso(),
        "workspace_file": str(dest),
        "payload": payload or {},
        "meta": meta or {},
    }
    ctx_path = _unique_path(outputs_dir / f"{base}.context.json")
    ctx_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        index_path = (outputs_dir / "README.md").resolve()
        try:
            _ = index_path.relative_to(workspace_root.resolve())
        except Exception:
            index_path = (outputs_dir / "README.md").resolve()
        entry = (
            f"- {utc_now_iso()} | {kind.upper()} | {title or ''} | "
            f"file: {dest.name} | context: {ctx_path.name} | source: {source}\n"
        )
        if not index_path.exists():
            index_path.write_text("# Outputs Index\n\n", encoding="utf-8")
        with index_path.open("a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass

    return {
        "workspace_path": str(dest),
        "workspace_context_path": str(ctx_path),
        "workspace_output_dir": str(outputs_dir),
    }
