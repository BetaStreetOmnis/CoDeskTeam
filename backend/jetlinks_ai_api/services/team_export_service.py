from __future__ import annotations

from pathlib import Path
from typing import Any

from ..db import fetchall, fetchone, row_to_dict, rows_to_dicts, utc_now_iso


def _md_escape_inline(value: str) -> str:
    # Markdown table-safe escaping for common characters.
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
    )


def _safe_text(value: object) -> str:
    return str(value or "").strip()


async def export_team_db_to_markdown(
    *,
    db: Any,
    team_id: int,
    team_name: str | None,
    user_email: str | None,
    user_name: str | None,
    workspace_root: Path,
    filename: str = "JETLINKS_AI_TEAM_DB.md",
) -> dict[str, object]:
    """
    Export team-scoped data to a Markdown file under workspace_root.

    This is meant for human review / sharing / versioning. It does not replace the DB.
    """
    root = workspace_root.expanduser().resolve()
    out_path = (root / filename).resolve()
    try:
        _ = out_path.relative_to(root)
    except Exception:
        raise ValueError("导出路径非法") from None

    now = utc_now_iso()

    # Settings (workspace path is stored in DB; "resolved workspace root" is a runtime value)
    ws_row = await fetchone(db, "SELECT workspace_path FROM team_settings WHERE team_id = ?", (int(team_id),))
    ws = row_to_dict(ws_row) or {}

    # Projects
    proj_rows = await fetchall(
        db,
        """
        SELECT id, name, slug, path, enabled, created_at, updated_at
        FROM team_projects
        WHERE team_id = ?
        ORDER BY id ASC
        """,
        (int(team_id),),
    )
    projects = rows_to_dicts(list(proj_rows))

    # Requirements
    req_rows = await fetchall(
        db,
        """
        SELECT id, project_id, source_team, title, description, status, priority, created_at, updated_at
        FROM team_requirements
        WHERE team_id = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (int(team_id),),
    )
    requirements = rows_to_dicts(list(req_rows))

    # Skills
    skill_rows = await fetchall(
        db,
        """
        SELECT id, name, description, enabled, content, created_at, updated_at
        FROM team_skills
        WHERE team_id = ?
        ORDER BY id DESC
        """,
        (int(team_id),),
    )
    skills = rows_to_dicts(list(skill_rows))

    lines: list[str] = []
    lines.append("# JetLinks AI Team DB Export")
    lines.append("")
    lines.append("> 说明：此文件由系统一键导出生成，用于审阅/共享/归档；主数据仍以数据库为准。")
    lines.append("")
    lines.append(f"- exported_at: `{now}`")
    lines.append(f"- team_id: `{int(team_id)}`")
    if team_name:
        lines.append(f"- team_name: `{_md_escape_inline(team_name)}`")
    if user_email or user_name:
        who = " / ".join([x for x in [_safe_text(user_name), _safe_text(user_email)] if x])
        lines.append(f"- exported_by: `{_md_escape_inline(who)}`")
    lines.append(f"- workspace_root: `{_md_escape_inline(str(root))}`")
    lines.append("")

    # Team settings
    lines.append("## Team Settings")
    lines.append("")
    workspace_path = _safe_text(ws.get("workspace_path"))
    lines.append(f"- workspace_path (db): `{_md_escape_inline(workspace_path or '(empty)')}`")
    lines.append("")

    # Projects
    lines.append("## Team Projects")
    lines.append("")
    if not projects:
        lines.append("- (empty)")
        lines.append("")
    else:
        lines.append("| id | name | slug | enabled | path | updated_at |")
        lines.append("|---:|---|---|:---:|---|---|")
        for p in projects:
            lines.append(
                "| %s | %s | %s | %s | %s | %s |"
                % (
                    int(p.get("id") or 0),
                    _md_escape_inline(_safe_text(p.get("name"))),
                    _md_escape_inline(_safe_text(p.get("slug"))),
                    "1" if bool(p.get("enabled")) else "0",
                    _md_escape_inline(_safe_text(p.get("path"))),
                    _md_escape_inline(_safe_text(p.get("updated_at"))),
                )
            )
        lines.append("")

    # Requirements
    lines.append("## Team Requirements")
    lines.append("")
    if not requirements:
        lines.append("- (empty)")
        lines.append("")
    else:
        lines.append("| id | project_id | status | priority | title | source_team | updated_at |")
        lines.append("|---:|---:|---|---|---|---|---|")
        for r in requirements:
            lines.append(
                "| %s | %s | %s | %s | %s | %s | %s |"
                % (
                    int(r.get("id") or 0),
                    int(r.get("project_id") or 0) if r.get("project_id") is not None else "",
                    _md_escape_inline(_safe_text(r.get("status"))),
                    _md_escape_inline(_safe_text(r.get("priority"))),
                    _md_escape_inline(_safe_text(r.get("title"))),
                    _md_escape_inline(_safe_text(r.get("source_team"))),
                    _md_escape_inline(_safe_text(r.get("updated_at"))),
                )
            )
        lines.append("")

        # Put full descriptions below to keep the table readable.
        lines.append("### Requirement Details")
        lines.append("")
        for r in requirements[:80]:
            rid = int(r.get("id") or 0)
            title = _safe_text(r.get("title"))
            desc = _safe_text(r.get("description"))
            if not desc:
                continue
            lines.append(f"#### #{rid} {title}")
            lines.append("")
            lines.append(desc)
            lines.append("")

    # Skills
    lines.append("## Team Skills")
    lines.append("")
    if not skills:
        lines.append("- (empty)")
        lines.append("")
    else:
        for s in skills:
            sid = int(s.get("id") or 0)
            name = _safe_text(s.get("name"))
            desc = _safe_text(s.get("description"))
            enabled = "enabled" if bool(s.get("enabled")) else "disabled"
            updated = _safe_text(s.get("updated_at"))
            lines.append(f"### {name or '未命名技能'} (`{enabled}`)")
            lines.append("")
            lines.append(f"- id: `{sid}`")
            if updated:
                lines.append(f"- updated_at: `{_md_escape_inline(updated)}`")
            if desc:
                lines.append(f"- description: `{_md_escape_inline(desc)}`")
            lines.append("")
            content = _safe_text(s.get("content"))
            if content:
                lines.append("#### Content")
                lines.append("")
                lines.append(content)
                lines.append("")

    text = "\n".join(lines).rstrip() + "\n"
    out_path.write_text(text, encoding="utf-8")

    try:
        size_bytes = out_path.stat().st_size
    except Exception:
        size_bytes = len(text.encode("utf-8", errors="ignore"))

    return {
        "ok": True,
        "updated_at": now,
        "workspace_root": str(root),
        "workspace_path": str(out_path),
        "bytes": int(size_bytes),
        "filename": str(out_path.name),
    }
