from __future__ import annotations

import re
import shutil
import time
from pathlib import Path


_GENERATED_FILE_RE = re.compile(r"^[a-f0-9]{32}\\.(pptx|docx|xlsx|zip|png|jpe?g|webp|gif)$", re.IGNORECASE)
_PROTOTYPE_DIR_RE = re.compile(r"^prototype_[a-f0-9]{32}$", re.IGNORECASE)

_LAST_RUN_AT: float | None = None


def cleanup_outputs_dir(outputs_dir: Path, *, ttl_seconds: int) -> dict:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    if ttl_seconds <= 0:
        return {"ok": True, "deleted_files": 0, "deleted_dirs": 0}

    now = time.time()
    deleted_files = 0
    deleted_dirs = 0

    for p in outputs_dir.iterdir():
        try:
            st = p.stat()
        except Exception:
            continue

        age = now - st.st_mtime
        if age <= ttl_seconds:
            continue

        if p.is_file() and _GENERATED_FILE_RE.match(p.name):
            try:
                p.unlink()
                deleted_files += 1
            except Exception:
                continue
        elif p.is_dir() and _PROTOTYPE_DIR_RE.match(p.name):
            try:
                shutil.rmtree(p, ignore_errors=True)
                deleted_dirs += 1
            except Exception:
                continue

    return {"ok": True, "deleted_files": deleted_files, "deleted_dirs": deleted_dirs}


def maybe_cleanup_outputs_dir(outputs_dir: Path, *, ttl_seconds: int, min_interval_seconds: int = 600) -> dict:
    global _LAST_RUN_AT
    now = time.time()
    if _LAST_RUN_AT is not None and (now - _LAST_RUN_AT) < min_interval_seconds:
        return {"ok": True, "skipped": True}

    _LAST_RUN_AT = now
    return cleanup_outputs_dir(outputs_dir, ttl_seconds=ttl_seconds)
