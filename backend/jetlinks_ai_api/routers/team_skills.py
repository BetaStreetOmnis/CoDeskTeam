from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..agent.providers.openai_provider import OpenAiProvider
from ..agent.tools.base import ToolDefinition
from ..agent.types import ChatMessage
from ..db import fetchall, fetchone, row_to_dict, rows_to_dicts, utc_now_iso
from ..deps import CurrentUser, get_current_user, get_db, get_settings, require_team_admin
from ..services.team_skill_seed_service import ensure_default_team_skills


router = APIRouter(tags=["team"])

class TeamSkill(BaseModel):
    id: int
    team_id: int
    name: str
    description: str
    content: str
    enabled: bool
    created_at: str
    updated_at: str


class CreateTeamSkillRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=200)
    content: str = Field(min_length=1, max_length=20_000)
    enabled: bool = True


class UpdateTeamSkillRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=20_000)
    enabled: bool | None = None


class AiDraftTeamSkillRequest(BaseModel):
    idea: str = Field(min_length=1, max_length=2000)
    name: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    draft: str | None = Field(default=None, max_length=20_000)
    model: str | None = Field(default=None, max_length=120)


class AiDraftTeamSkillResponse(BaseModel):
    name: str
    description: str
    content: str


class _TeamSkillDraftToolArgs(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=200)
    content: str = Field(min_length=1, max_length=20_000)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _extract_json_object(text: str) -> dict | None:
    t = (text or "").strip()
    if not t:
        return None

    try:
        v = json.loads(t)
        return v if isinstance(v, dict) else None
    except Exception:
        pass

    m = _JSON_FENCE_RE.search(t)
    if m:
        try:
            v = json.loads(m.group(1))
            return v if isinstance(v, dict) else None
        except Exception:
            pass

    start = t.find("{")
    end = t.rfind("}")
    if start >= 0 and end > start:
        snippet = t[start : end + 1]
        try:
            v = json.loads(snippet)
            return v if isinstance(v, dict) else None
        except Exception:
            return None

    return None


@router.get("/team/skills", response_model=list[TeamSkill])
async def list_team_skills(user: CurrentUser = Depends(get_current_user), db=Depends(get_db)) -> list[TeamSkill]:  # noqa: ANN001
    # Best-effort seed defaults so a fresh team has something to toggle immediately.
    try:
        await ensure_default_team_skills(db, team_id=user.team_id)
    except Exception:
        pass

    rows = await fetchall(
        db,
        """
        SELECT id, team_id, name, description, content, enabled, created_at, updated_at
        FROM team_skills
        WHERE team_id = ?
        ORDER BY id DESC
        """,
        (user.team_id,),
    )
    items = rows_to_dicts(list(rows))
    for it in items:
        it["enabled"] = bool(it.get("enabled"))
    return [TeamSkill(**it) for it in items]


@router.post("/team/skills/ai-draft", response_model=AiDraftTeamSkillResponse)
async def ai_draft_team_skill(
    req: AiDraftTeamSkillRequest,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
) -> AiDraftTeamSkillResponse:
    require_team_admin(user)

    if not getattr(settings, "openai_api_key", None):
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY 未配置")

    provider = OpenAiProvider(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    used_model = (req.model or settings.model or "").strip() or "gpt-5.2"

    async def _noop_handler(_args: BaseModel, _ctx):  # noqa: ANN001
        return {"ok": True}

    draft_tool = ToolDefinition(
        name="team_skill_draft",
        description="Return the drafted team skill with fields: name, description, content.",
        risk="safe",
        input_model=_TeamSkillDraftToolArgs,
        handler=_noop_handler,
        parameters_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "minLength": 1, "maxLength": 80},
                "description": {"type": "string", "maxLength": 200},
                "content": {"type": "string", "minLength": 1, "maxLength": 20000},
            },
            "required": ["name", "content"],
        },
    )

    system = (
        "你是一名提示词工程师，要帮团队生成「团队技能/团队规范」文本（将被注入到系统提示词）。\n"
        "请遵守：\n"
        "- 必须调用工具 team_skill_draft 且只调用一次；不要输出其他文本。\n"
        "- 工具参数必须包含：name, description, content。\n"
        "- content 用 Markdown，面向 AI 助手的可执行规则（清晰、可操作、可检查）。\n"
        "- 语言：中文。\n"
        "- 不要包含任何密钥/账号/URL Token 等敏感信息；不要指示泄露 secrets。\n"
        "- 尽量 30~120 行，结构建议：目标、适用范围、规则、示例、反例。\n"
        "请开始。"
    ).strip()

    draft = (req.draft or "").strip()
    name = (req.name or "").strip()
    desc = (req.description or "").strip()

    user_text = (
        f"团队：{user.team_name}\n"
        f"需求：{req.idea.strip()}\n"
        f"建议名称：{name or '（空）'}\n"
        f"建议说明：{desc or '（空）'}\n"
        + (f"\n已有草稿（可参考/重写）：\n{draft}\n" if draft else "")
    ).strip()

    resp = await provider.complete(
        model=used_model,
        messages=[ChatMessage(role="system", content=system), ChatMessage(role="user", content=user_text)],
        tools=[draft_tool],
    )

    if resp.tool_calls:
        # Prefer structured tool-call output.
        for tc in resp.tool_calls:
            if tc.name != "team_skill_draft":
                continue
            try:
                args = json.loads(tc.arguments_json or "{}")
                parsed = _TeamSkillDraftToolArgs.model_validate(args)
                return AiDraftTeamSkillResponse(name=parsed.name, description=parsed.description, content=parsed.content)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"AI 返回 tool 参数解析失败：{e}") from e

    # Fallback: attempt to parse free-form JSON.
    raw = (resp.assistant_text or "").strip()
    if not raw:
        raise HTTPException(status_code=500, detail="AI 未返回可用内容")

    obj = _extract_json_object(raw)
    if not obj:
        raise HTTPException(status_code=500, detail=f"AI 返回格式不正确：{raw[:400]}")

    out_name = str(obj.get("name") or name or "团队技能").strip()
    out_desc = str(obj.get("description") or desc or "").strip()
    out_content = str(obj.get("content") or "").strip()

    if not out_content:
        raise HTTPException(status_code=500, detail="AI 返回缺少 content")

    out_name = out_name[:80] if len(out_name) > 80 else out_name
    out_desc = out_desc[:200] if len(out_desc) > 200 else out_desc
    if len(out_content) > 20_000:
        out_content = out_content[:19_900].rstrip() + "\n\n（内容过长已截断）"

    return AiDraftTeamSkillResponse(name=out_name, description=out_desc, content=out_content)


@router.post("/team/skills", response_model=TeamSkill)
async def create_team_skill(
    req: CreateTeamSkillRequest,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> TeamSkill:
    require_team_admin(user)
    now = utc_now_iso()
    cur = await db.execute(
        """
        INSERT INTO team_skills(team_id, name, description, content, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user.team_id, req.name.strip(), req.description.strip(), req.content, 1 if req.enabled else 0, now, now),
    )
    skill_id = int(cur.lastrowid)
    await db.commit()

    row = await fetchone(
        db,
        """
        SELECT id, team_id, name, description, content, enabled, created_at, updated_at
        FROM team_skills
        WHERE id = ?
        """,
        (skill_id,),
    )
    data = row_to_dict(row)
    if not data:
        raise HTTPException(status_code=500, detail="创建失败")
    data["enabled"] = bool(data.get("enabled"))
    return TeamSkill(**data)


@router.put("/team/skills/{skill_id}", response_model=TeamSkill)
async def update_team_skill(
    skill_id: int,
    req: UpdateTeamSkillRequest,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> TeamSkill:
    require_team_admin(user)
    existing_row = await fetchone(
        db,
        "SELECT id, team_id FROM team_skills WHERE id = ?",
        (int(skill_id),),
    )
    existing = row_to_dict(existing_row)
    if not existing or int(existing["team_id"]) != user.team_id:
        raise HTTPException(status_code=404, detail="技能不存在")

    fields: list[str] = []
    values: list = []
    if req.name is not None:
        fields.append("name = ?")
        values.append(req.name.strip())
    if req.description is not None:
        fields.append("description = ?")
        values.append(req.description.strip())
    if req.content is not None:
        fields.append("content = ?")
        values.append(req.content)
    if req.enabled is not None:
        fields.append("enabled = ?")
        values.append(1 if req.enabled else 0)

    if not fields:
        row = await fetchone(
            db,
            """
            SELECT id, team_id, name, description, content, enabled, created_at, updated_at
            FROM team_skills
            WHERE id = ?
            """,
            (int(skill_id),),
        )
        data = row_to_dict(row)
        if not data:
            raise HTTPException(status_code=404, detail="技能不存在")
        data["enabled"] = bool(data.get("enabled"))
        return TeamSkill(**data)

    fields.append("updated_at = ?")
    values.append(utc_now_iso())
    values.append(int(skill_id))

    await db.execute(f"UPDATE team_skills SET {', '.join(fields)} WHERE id = ?", tuple(values))
    await db.commit()

    row = await fetchone(
        db,
        """
        SELECT id, team_id, name, description, content, enabled, created_at, updated_at
        FROM team_skills
        WHERE id = ?
        """,
        (int(skill_id),),
    )
    data = row_to_dict(row)
    if not data:
        raise HTTPException(status_code=404, detail="技能不存在")
    data["enabled"] = bool(data.get("enabled"))
    return TeamSkill(**data)


@router.delete("/team/skills/{skill_id}")
async def delete_team_skill(
    skill_id: int,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    require_team_admin(user)
    existing_row = await fetchone(
        db,
        "SELECT id, team_id FROM team_skills WHERE id = ?",
        (int(skill_id),),
    )
    existing = row_to_dict(existing_row)
    if not existing or int(existing["team_id"]) != user.team_id:
        raise HTTPException(status_code=404, detail="技能不存在")

    await db.execute("DELETE FROM team_skills WHERE id = ?", (int(skill_id),))
    await db.commit()
    return {"ok": True}
