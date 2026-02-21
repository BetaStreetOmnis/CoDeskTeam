from __future__ import annotations

from typing import Any

from ..db import fetchall, rows_to_dicts, utc_now_iso


_DEFAULT_SKILL_PACK_MARKER = "<!-- aistaff:default_team_skill_pack=park_quote_v1 -->"

_PARK_QUOTE_MODULES_V1: list[dict[str, str]] = [
    {"name": "小红书自动化发布系统", "level1": "AI运营工具"},
    {"name": "公众号管理与自动化推送", "level1": "AI运营工具"},
    {"name": "营销物料智能设计", "level1": "AI运营工具"},
    {"name": "市场分析系统", "level1": "市场与商机洞察"},
    {"name": "报价文件自动生成", "level1": "文档生成"},
    {"name": "投标文件智能生成与审查", "level1": "文档生成"},
    {"name": "商务文件格式化生成器", "level1": "文档生成"},
    {"name": "企业知识库智能构建", "level1": "私有知识库构建与应用"},
    {"name": "客户经营分析工具", "level1": "私有知识库构建与应用"},
    {"name": "员工效率工具集成", "level1": "员工效率工具集成"},
    {"name": "智能舆情监控系统", "level1": "员工效率工具集成"},
    {"name": "会议纪要智能生成", "level1": "员工效率工具集成"},
    {"name": "智能问数（chatbi）", "level1": "员工效率工具集成"},
]


def _render_park_quote_skill_content(*, name: str, level1: str) -> str:
    # Keep this short by default: team skills are injected into the system prompt when enabled.
    # Users can expand/replace with a full template later (e.g. importing from an XLSX template).
    return (
        f"{_DEFAULT_SKILL_PACK_MARKER}\n"
        f"\n"
        f"## 模块\n"
        f"- 一级功能：{level1}\n"
        f"- 二级模块：{name}\n"
        f"\n"
        f"## 你需要做什么\n"
        f"- 当用户提到该模块时，先澄清范围（目标用户/场景/端：Web/移动端/小程序/内网）、集成系统与数据源、权限与审计、交付里程碑与验收标准。\n"
        f"- 优先输出结构化结果：需求拆解清单、风险与假设、以及可直接落到报价的工作量清单。\n"
        f"\n"
        f"## 报价输出格式（建议）\n"
        f"- 用表格输出：`三级功能 | 功能描述 | 单位 | 数量 | 单价 | 总价 | 备注`\n"
        f"- 默认单位可先用 `人月`；如需按 `套/年/台/次` 等计价，必须向用户确认口径。\n"
        f"- 用户未给数量/单价：先追问；也可以先用 `0` 占位并在备注标注 `待确认`。\n"
        f"\n"
        f"## 与工作区文件对齐\n"
        f"- 如果工作区/附件里存在历史报价单或需求说明（如 `*报价*.xlsx`、`README.md`），先读取并沿用其字段命名、模块层级与口径。\n"
    ).strip()


async def ensure_default_team_skills(db: Any, *, team_id: int) -> int:
    """
    Idempotently seed default (disabled) team skills for a team.
    If the default pack has been seeded before:
    - We do not re-add deleted defaults (to respect manual customization).
    - We prune skills from the same seeded pack that are no longer part of the default list.
    Returns number of inserted skills.
    """
    rows = await fetchall(db, "SELECT id, name, content FROM team_skills WHERE team_id = ?", (int(team_id),))
    existing_rows = rows_to_dicts(list(rows))
    desired = {str(m.get("name") or "").strip() for m in _PARK_QUOTE_MODULES_V1 if str(m.get("name") or "").strip()}

    seeded = [
        r
        for r in existing_rows
        if _DEFAULT_SKILL_PACK_MARKER in str(r.get("content") or "")
    ]
    if seeded:
        # Prune items from the previously-seeded pack that are no longer desired.
        # This keeps "default pack" aligned across upgrades, without touching user-created skills.
        ids_to_delete: list[int] = []
        for r in seeded:
            name = str(r.get("name") or "").strip()
            if name and name not in desired:
                try:
                    ids_to_delete.append(int(r.get("id")))
                except Exception:
                    continue

        if ids_to_delete:
            placeholders = ", ".join(["?"] * len(ids_to_delete))
            await db.execute(
                f"DELETE FROM team_skills WHERE team_id = ? AND id IN ({placeholders})",
                [int(team_id), *ids_to_delete],
            )
            await db.commit()
        return 0

    existing = {str(r.get("name") or "").strip() for r in existing_rows}

    now = utc_now_iso()
    inserted = 0
    for mod in _PARK_QUOTE_MODULES_V1:
        name = str(mod["name"]).strip()
        if not name or name in existing:
            continue
        level1 = str(mod.get("level1") or "").strip()
        description = f"园区智能化报价模块 · {level1} / 二级模块（默认关闭，按需启用）".strip()
        content = _render_park_quote_skill_content(name=name, level1=level1 or "（未分类）")

        await db.execute(
            """
            INSERT INTO team_skills(team_id, name, description, content, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (int(team_id), name, description, content, 0, now, now),
        )
        inserted += 1

    if inserted:
        await db.commit()
    return inserted
