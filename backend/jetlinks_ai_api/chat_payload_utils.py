from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


_FILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


def safe_outputs_path(outputs_dir: Path, file_id: str) -> Path:
    normalized_file_id = (file_id or "").strip()
    if not normalized_file_id:
        raise ValueError("invalid file_id")
    if not _FILE_ID_RE.match(normalized_file_id) or ".." in normalized_file_id:
        raise ValueError("invalid file_id")

    base = outputs_dir.resolve()
    full = (base / normalized_file_id).resolve()
    if full == base or not str(full).startswith(str(base) + os.sep):
        raise ValueError("invalid file_id")
    return full


def truncate_title(text: str, max_len: int = 48) -> str:
    normalized = (text or "").strip().replace("\n", " ").replace("\r", " ")
    normalized = " ".join(normalized.split())
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max(0, max_len - 1)] + "…"


def infer_attachment_kind(attachment: dict[str, Any]) -> str:
    kind = str(attachment.get("kind") or attachment.get("type") or "").strip().lower()
    if kind in {"image", "file"}:
        return kind
    content_type = str(attachment.get("content_type") or "").strip().lower()
    if content_type.startswith("image/"):
        return "image"
    file_id = str(attachment.get("file_id") or "").lower()
    if file_id.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image"
    return "file"


def safe_load_attachments(value: object) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]
    return []
