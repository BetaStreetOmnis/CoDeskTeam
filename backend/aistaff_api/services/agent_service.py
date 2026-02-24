from __future__ import annotations

import re
from typing import Any
from uuid import uuid4
from pathlib import Path
from datetime import datetime, timezone

from ..config import Settings
from ..agent.prompt import build_system_prompt
from ..agent.run_task import run_agent_task
from ..agent.types import ChatMessage
from ..agent.providers.openai_provider import OpenAiProvider
from ..agent.providers.mock_provider import MockProvider
from ..agent.tools.base import ToolContext, ToolDefinition
from ..agent.tools.fs_tools import fs_list_tool, fs_read_tool, fs_write_tool
from ..agent.tools.shell_tools import shell_run_tool
from ..agent.tools.doc_tools import (
    doc_pptx_create_tool,
    doc_quote_docx_create_tool,
    doc_quote_xlsx_create_tool,
    doc_inspection_docx_create_tool,
    doc_inspection_xlsx_create_tool,
)
from ..agent.tools.attachment_tools import attachment_read_tool
from ..agent.tools.browser_tools import browser_start_tool, browser_navigate_tool, browser_screenshot_tool
from ..agent.tools.prototype_tools import proto_generate_tool
from ..session_store import get_session_store
from .opencode_service import OpencodeService
from .nanobot_service import NanobotService
from .codex_service import CodexService
from .pi_service import PiService


_TEAM_SKILLS_MARKER = "【团队技能】"
_RUNTIME_MARKER = "【运行信息】"
_SUMMARY_MARKER = "【思路摘要】"
_PPT_EXPLICIT_RE = re.compile(r"(pptx?|幻灯片|演示文稿|slides?)", re.IGNORECASE)
_PPT_PAGE_COUNT_RE = re.compile(r"(\d{1,2})\s*(页|张)", re.IGNORECASE)
_PPT_CONTEXT_RE = re.compile(r"(培训|课件|汇报|演示|宣讲|分享|路演|方案)", re.IGNORECASE)
_PPT_MODE_MARKER = "【PPT_MODE】"

_QUOTE_EXPLICIT_RE = re.compile(r"(报价单|报价表|quotation)", re.IGNORECASE)
_QUOTE_MODE_MARKER = "【QUOTE_MODE】"

_INSPECTION_EXPLICIT_RE = re.compile(r"(报检单|报验单|检验单|报检表|报验表|质检单|验收报验)", re.IGNORECASE)
_INSPECTION_DOCX_RE = re.compile(r"(docx|word)", re.IGNORECASE)
_INSPECTION_XLSX_RE = re.compile(r"(xlsx|excel)", re.IGNORECASE)
_INSPECTION_MODE_MARKER = "【INSPECTION_MODE】"

_PROTO_EXPLICIT_RE = re.compile(r"(原型|prototype|h5\\s*原型|html\\s*(原型|页面|界面)|(页面|界面)\\s*html)", re.IGNORECASE)
_PROTO_MODE_MARKER = "【PROTO_MODE】"


def _runtime_system_prompt(*, provider: str, model: str, workspace: Path, tool_ctx: ToolContext) -> str:
    now = datetime.now(timezone.utc).astimezone()
    enabled = []
    if tool_ctx.enable_shell:
        enabled.append("shell_run")
    if tool_ctx.enable_write:
        enabled.append("fs_write")
    if tool_ctx.enable_browser:
        enabled.append("browser_*")
    enabled_text = ", ".join(enabled) if enabled else "（无）"
    return (
        f"{_RUNTIME_MARKER}\n"
        f"- Time: {now.isoformat(timespec='seconds')}\n"
        f"- Provider: {provider}\n"
        f"- Model: {model}\n"
        f"- Workspace: {workspace}\n"
        f"- Dangerous tools enabled: {enabled_text}\n"
    ).strip()


def _extract_requested_pages(message: str) -> int | None:
    m = _PPT_PAGE_COUNT_RE.search(message or "")
    if not m:
        return None
    try:
        n = int(m.group(1))
    except Exception:
        return None
    if n <= 0 or n > 50:
        return None
    return n


def _ppt_request(message: str) -> tuple[bool, int | None]:
    text = (message or "").strip()
    if not text:
        return False, None
    if _PPT_EXPLICIT_RE.search(text):
        return True, _extract_requested_pages(text)
    pages = _extract_requested_pages(text)
    if pages and _PPT_CONTEXT_RE.search(text):
        return True, pages
    return False, None


def _ppt_system_instruction(pages: int | None) -> str:
    total = pages or 8
    content_slides = max(1, total - 1)
    return (
        f"{_PPT_MODE_MARKER}\n"
        "用户在请求生成一份 PPT（PPTX）。你必须调用工具 `doc_pptx_create` 生成文件，并在最终回复中给出下载链接。\n"
        "- `doc_pptx_create` 支持可选参数：`style`（auto/modern_blue/minimal_gray/dark_tech/warm_business/template_jetlinks/template_team）和 `layout_mode`（auto/focus/single_column/two_column/cards）。\n"
        "- 如用户提供/上传了 PPTX 模板（file_id 以 .pptx 结尾），可用 `template_file_id` 指定模板；必要时可补充 `template_content_indices`（内容页索引，1-based）与 `template_keep_images`。\n"
        "- 若用户提出风格诉求（如深色、极简、科技蓝、企业蓝、暖色商务、卡片化），请显式传对应 `style` / `layout_mode`。\n"
        "- 除非用户明确要求定制，否则不要在生成前反复提问；信息不全也先生成“全员通用版”。默认：受众=公司员工，时长=60分钟，方向=通识入门+办公提效+安全合规。\n"
        "- 如需确认，仅允许在生成后追加 1 个可选问题用于二次优化。\n"
        f"- 目标总页数：{total} 页（包含 1 页封面）。工具会自动生成封面，因此你需要在 `slides` 中提供 {content_slides} 页内容。\n"
        "- 每页标题要具体（避免‘概述/总结’空标题），优先‘问题/方法/动作/收益’表述。\n"
        "- 每页 3–6 条要点；每条控制在 10–28 个中文字符，尽量用动词开头（例如：明确/建立/推进/复盘）。\n"
        "- 页间结构建议：背景与目标 → 方法与步骤 → 场景案例 → 落地计划与里程碑。\n"
        "- 避免堆砌定义；每页至少有 1 条可执行动作或可量化结果。\n"
        "- 输出语言：中文。\n"
        "- 不要输出长篇正文，优先生成 PPT 文件。\n"
    )


def _quote_request(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return bool(_QUOTE_EXPLICIT_RE.search(text))


def _quote_system_instruction() -> str:
    return (
        f"{_QUOTE_MODE_MARKER}\n"
        "用户在请求生成一份报价单文件。你必须调用报价单工具生成文件，并在最终回复中给出下载链接。\n"
        "- 默认优先生成 Excel（XLSX）：调用 `doc_quote_xlsx_create`。\n"
        "- 如用户明确要求 Word：调用 `doc_quote_docx_create`。\n"
        "- 必需字段：seller、buyer、items（每项包含 name/quantity/unit_price；unit 可选）。\n"
        "- 为避免来回追问：如果用户未提供 seller/buyer，使用占位值（seller=某某科技有限公司，buyer=某某客户）。\n"
        "- 如果某个条目缺 quantity 或 unit_price：用 0 占位并生成文件，同时在 note/备注里列出“待补齐字段清单”。\n"
        "- 仅允许在生成后追加 1 个可选问题，用于让用户补齐真实数量/单价并二次生成正式版。\n"
        "- 输出语言：中文。\n"
    )


def _pptx_template_from_attachments(attachments: list[dict] | None) -> str | None:
    for att in attachments or []:
        if not isinstance(att, dict):
            continue
        file_id = str(att.get("file_id") or "").strip()
        filename = str(att.get("filename") or "").strip()
        if file_id.lower().endswith(".pptx") or filename.lower().endswith(".pptx"):
            return file_id or None
    return None


_QUOTE_LINE_PREFIX_RE = re.compile(r"^\s*(?:[-*•·]+|\d+[.)、])\s*")
_QUOTE_QTY_VALUE_RE = re.compile(r"数量\s*[:=：]\s*([^，,;；]*)")
_QUOTE_PRICE_VALUE_RE = re.compile(r"(?:单价|价格)\s*[:=：]\s*([^，,;；]*)")
_QUOTE_UNIT_VALUE_RE = re.compile(r"单位\s*[:=：]\s*([^，,;；\s]+)")


def _parse_number(value: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", str(value or ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _parse_quote_items_from_message(message: str) -> tuple[list[dict[str, object]], list[str]]:
    """
    Best-effort parse of a quote/quotation item list from the user's free-form text.

    If parsing fails, we still return a single placeholder row to avoid blocking output generation.
    """

    items: list[dict[str, object]] = []
    missing: list[str] = []

    for raw in (message or "").splitlines():
        line = str(raw or "").strip()
        if not line:
            continue
        if "数量" not in line and "单价" not in line and "价格" not in line:
            continue

        line = _QUOTE_LINE_PREFIX_RE.sub("", line).strip()
        if not line:
            continue

        name_part = re.split(r"(?:数量\s*[:=：]|单价\s*[:=：]|价格\s*[:=：])", line, maxsplit=1)[0]
        name = str(name_part or "").strip().rstrip("，,;；:：")
        if not name:
            continue

        qty: float | None = None
        price: float | None = None
        unit = "项"

        m_qty = _QUOTE_QTY_VALUE_RE.search(line)
        if m_qty:
            qty = _parse_number(m_qty.group(1))

        m_price = _QUOTE_PRICE_VALUE_RE.search(line)
        if m_price:
            price = _parse_number(m_price.group(1))

        m_unit = _QUOTE_UNIT_VALUE_RE.search(line)
        if m_unit:
            unit_value = str(m_unit.group(1) or "").strip()
            if unit_value:
                unit = unit_value

        if qty is None:
            missing.append(f"{name}：数量")
            qty = 0.0
        if price is None:
            missing.append(f"{name}：单价")
            price = 0.0

        items.append(
            {
                "name": name,
                "quantity": float(qty),
                "unit_price": float(price),
                "unit": unit,
            }
        )

    if not items:
        items = [{"name": "（请填写条目）", "quantity": 0.0, "unit_price": 0.0, "unit": "项"}]
        missing.append("（请填写条目）：数量/单价")

    # Deduplicate while preserving order.
    missing = list(dict.fromkeys([str(x) for x in missing if str(x).strip()]))
    return items, missing


def _inspection_request(message: str) -> str | None:
    text = (message or "").strip()
    if not text:
        return None
    if not _INSPECTION_EXPLICIT_RE.search(text):
        return None
    if _INSPECTION_XLSX_RE.search(text):
        return "xlsx"
    if _INSPECTION_DOCX_RE.search(text):
        return "docx"
    return "docx"


def _inspection_system_instruction(fmt: str) -> str:
    tool = "doc_inspection_xlsx_create" if fmt == "xlsx" else "doc_inspection_docx_create"
    return (
        f"{_INSPECTION_MODE_MARKER}\n"
        "用户在请求生成一份报检单/检验单文件。你必须调用对应工具生成文件，并在最终回复中给出下载链接。\n"
        f"- 默认生成格式：{fmt.upper()}（工具：`{tool}`）。如用户要求另一种格式，请选择对应工具。\n"
        "- 即使信息不全，也要先生成“通用模板”（未知字段可留空或填“—”）；生成后再提出补充问题用于二次迭代。\n"
        "- 输出语言：中文。\n"
        "- 不要输出长篇正文，优先生成文件。\n"
    )


def _proto_request(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return bool(_PROTO_EXPLICIT_RE.search(text))


def _proto_system_instruction() -> str:
    return (
        f"{_PROTO_MODE_MARKER}\n"
        "用户在请求生成一份原型页面（HTML ZIP）。你必须调用工具 `proto_generate` 生成文件，并在最终回复中给出下载链接。\n"
        "- 需要 project_name 与 pages（每页 title 必填，description 可选）。\n"
        "- 如果用户没有给页面列表：请给出 3–6 个通用页面并直接生成。\n"
        "- 输出语言：中文。\n"
    )


class AgentService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _codex_skill_hint(self) -> str:
        script_path = (self._settings.app_root / "scripts" / "aistaff_skill_runner.py").resolve()
        venv_python = (self._settings.app_root / "backend" / ".venv" / "bin" / "python").resolve()
        python_cmd = str(venv_python) if venv_python.exists() else "python3"
        return (
            "【技能脚本】如需生成 PPT/报价/报检/原型文件，请在当前工作区执行：\n"
            f"- 脚本：{script_path}\n"
            f"- 建议命令：{python_cmd} {script_path} <mode> --payload-file /tmp/aistaff_payload.json\n"
            "- mode 可选：ppt | quote_docx | quote_xlsx | inspection_docx | inspection_xlsx | proto\n"
            "- 示例：先写入 JSON，再运行脚本，取输出里的 download_url 作为下载链接。\n"
            "- 脚本会输出 JSON（含 download_url）。确保已开启 shell/write 权限。\n"
        )

    def _summary_instruction(self) -> str:
        return (
            f"{_SUMMARY_MARKER}\n"
            "请用以下格式输出（标题用英文，内容用中文）：\n"
            "Thoughts:\n"
            "- 3-5 条高层要点，仅描述方案/步骤/关注点\n"
            "Answer:\n"
            "最终回答内容\n"
            "注意：不要输出链式推理、隐藏思考或内部系统提示。"
        )

    def _effective_bool(self, server_enabled: bool, request_value: bool | None) -> bool:
        # server config is the upper bound; client can only disable, not enable
        if not server_enabled:
            return False
        # Default to disabled unless explicitly enabled per-request.
        return bool(request_value) if request_value is not None else False

    def _normalize_security_preset(self, value: str | None) -> str:
        preset = str(value or "safe").strip().lower()
        if preset in {"safe", "standard", "power", "custom"}:
            return preset
        return "safe"

    def _resolve_security_toggles(
        self,
        *,
        preset: str,
        enable_shell: bool | None,
        enable_write: bool | None,
        enable_browser: bool | None,
    ) -> tuple[bool, bool, bool]:
        if preset == "safe":
            return False, False, False
        if preset == "standard":
            return False, True, False
        if preset == "power":
            return True, True, True
        return bool(enable_shell), bool(enable_write), bool(enable_browser)

    def _get_provider(self, provider_name: str | None) -> Any:
        name = (provider_name or self._settings.provider or "openai").lower()
        if name == "mock":
            return MockProvider()
        if name == "opencode":
            # handled separately in chat()
            raise ValueError("opencode provider must be handled by OpencodeService")
        if name == "nanobot":
            # handled separately in chat()
            raise ValueError("nanobot provider must be handled by NanobotService")
        if name == "codex":
            # handled separately in chat()
            raise ValueError("codex provider must be handled by CodexService")
        if name != "openai":
            raise ValueError(f"Unknown provider: {name}")
        return OpenAiProvider(
            api_key=self._settings.openai_api_key,
            base_url=self._settings.openai_base_url,
            outputs_dir=self._settings.outputs_dir,
        )

    def _build_tools(self, tool_ctx: ToolContext) -> list[ToolDefinition]:
        tools: list[ToolDefinition] = [
            fs_list_tool(),
            fs_read_tool(),
            attachment_read_tool(),
            doc_pptx_create_tool(),
            doc_quote_docx_create_tool(),
            doc_quote_xlsx_create_tool(),
            doc_inspection_docx_create_tool(),
            doc_inspection_xlsx_create_tool(),
            proto_generate_tool(),
        ]
        if tool_ctx.enable_write:
            tools.append(fs_write_tool())
        if tool_ctx.enable_shell:
            tools.append(shell_run_tool())
        if tool_ctx.enable_browser:
            tools.extend([browser_start_tool(), browser_navigate_tool(), browser_screenshot_tool()])
        return tools

    async def chat(
        self,
        *,
        message: str,
        session_id: str | None,
        role: str,
        user_id: int,
        team_id: int,
        provider: str | None,
        model: str | None,
        workspace_root: Path,
        security_preset: str | None,
        enable_shell: bool | None,
        enable_write: bool | None,
        enable_browser: bool | None,
        enable_dangerous: bool | None,
        show_reasoning: bool | None,
        attachments: list[dict] | None,
        team_skills_prompt: str | None = None,
    ) -> dict:
        if not message.strip():
            raise ValueError("message is empty")

        sid = session_id or uuid4().hex
        workspace = (workspace_root or self._settings.workspace_root).resolve()

        store = get_session_store()
        provider_name = (provider or self._settings.provider or "openai").lower()

        security_profile = self._normalize_security_preset(security_preset)
        requested_shell, requested_write, requested_browser = self._resolve_security_toggles(
            preset=security_profile,
            enable_shell=enable_shell,
            enable_write=enable_write,
            enable_browser=enable_browser,
        )
        effective_shell = self._effective_bool(self._settings.enable_shell, requested_shell)
        effective_write = self._effective_bool(self._settings.enable_write, requested_write)
        effective_browser = self._effective_bool(self._settings.enable_browser, requested_browser)

        summary_text = self._summary_instruction() if show_reasoning else ""

        if provider_name == "codex":
            # Keep aistaff session ownership/TTL, but delegate execution to Codex CLI.
            session = await store.get_or_create(
                session_id=sid,
                user_id=user_id,
                team_id=team_id,
                role=role,
                system_prompt=f"codex:{role}",
                workspace_root=str(workspace),
                ttl_seconds=max(0, int(self._settings.session_ttl_minutes)) * 60,
                max_sessions=max(0, int(self._settings.max_sessions)),
            )

            extra_system = ""
            if team_skills_prompt and team_skills_prompt.strip():
                extra_system = team_skills_prompt.strip()
            if summary_text:
                extra_system = f"{extra_system}\n\n{summary_text}" if extra_system else summary_text

            is_ppt, ppt_pages = _ppt_request(message)
            is_quote = _quote_request(message)
            inspect_fmt = _inspection_request(message)
            is_inspection = inspect_fmt is not None
            is_proto = _proto_request(message)
            requested_dangerous = bool(enable_dangerous)

            # Codex CLI doesn't support aistaff's doc/prototype tools.
            # For these requests, fall back to aistaff's own agent loop (OpenAI provider + tools)
            # so users can generate artifacts even when shell/write is disabled.
            if is_ppt or is_quote or is_inspection or is_proto:
                # Fast-path: for simple quote requests without attachments, generate a draft XLSX directly
                # (fill missing quantity/unit_price with 0 and add a note) to avoid back-and-forth questions.
                if is_quote and not (is_ppt or is_inspection or is_proto) and not attachments:
                    items, missing = _parse_quote_items_from_message(message)
                    note = ""
                    if missing:
                        note = f"缺失项已用 0 占位，待补齐：{'；'.join(missing)}"

                    args = {
                        "seller": "某某科技有限公司",
                        "buyer": "某某客户",
                        "currency": "CNY",
                        "items": items,
                        "note": note or None,
                    }

                    tool_ctx = ToolContext(
                        session_id=sid,
                        workspace_root=workspace,
                        outputs_dir=self._settings.outputs_dir,
                        enable_shell=False,
                        enable_write=False,
                        enable_browser=False,
                        max_file_read_chars=self._settings.max_file_read_chars,
                        max_tool_output_chars=self._settings.max_tool_output_chars,
                        max_context_chars=max(0, int(self._settings.max_context_chars)),
                    )

                    tool = doc_quote_xlsx_create_tool()
                    parsed = tool.input_model.model_validate(args)
                    meta = await tool.handler(parsed, tool_ctx)

                    download_url = str(meta.get("download_url") or "").strip()
                    missing_lines = "\n".join([f"- {m}" for m in missing]) if missing else ""

                    if show_reasoning:
                        assistant = (
                            "Thoughts\n"
                            "- 已按清单生成报价单 Excel（缺失项用 0 占位）\n"
                            "- 待补齐字段已写入备注，方便你快速改成正式版\n"
                            "- 你补齐数量/单价后我可以立刻重生成一份正式报价\n\n"
                            "Answer\n"
                            f"已生成报价单 Excel（XLSX）。\n\n下载：{download_url or '（生成成功但未返回下载链接）'}"
                        ).strip()
                    else:
                        assistant = f"已生成报价单 Excel（XLSX）。\n\n下载：{download_url or '（生成成功但未返回下载链接）'}".strip()

                    if missing_lines:
                        assistant = f"{assistant}\n\n待补齐：\n{missing_lines}".strip()

                    events: list[dict[str, Any]] = [
                        {
                            "type": "security_profile",
                            "preset": security_profile,
                            "requested": {
                                "shell": requested_shell,
                                "write": requested_write,
                                "browser": requested_browser,
                                "dangerous": requested_dangerous,
                            },
                            "effective": {
                                "shell": False,
                                "write": False,
                                "browser": False,
                                "dangerous": False,
                            },
                        },
                        {"type": "codex_fallback", "provider": "builtin", "requested": ["quote"]},
                        {"type": "tool_call", "tool": "doc_quote_xlsx_create", "args": args},
                        {"type": "tool_result", "tool": "doc_quote_xlsx_create", "result": meta},
                    ]

                    await store.update_messages(
                        session_id=sid,
                        user_id=user_id,
                        team_id=team_id,
                        messages=[
                            *session.messages,
                            ChatMessage(role="user", content=message, attachments=attachments or None),
                            ChatMessage(role="assistant", content=assistant),
                        ],
                        max_messages=max(0, int(self._settings.max_session_messages)),
                        max_chars=max(0, int(self._settings.max_context_chars)),
                    )

                    return {"session_id": sid, "assistant": assistant, "events": events, "opencode_session_id": None}

                system_prompt = await build_system_prompt(self._settings.app_root, workspace, role)
                messages: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
                if extra_system:
                    messages.append(ChatMessage(role="system", content=extra_system))

                used_model = (model or self._settings.model or "gpt-5.2").strip() or "gpt-5.2"
                if "codex" in used_model.lower():
                    used_model = "gpt-5.2"

                requested: list[str] = []
                tools: list[ToolDefinition] = [fs_list_tool(), fs_read_tool(), attachment_read_tool()]
                if is_ppt:
                    requested.append("ppt")
                    messages.append(ChatMessage(role="system", content=_ppt_system_instruction(ppt_pages)))
                    tools.append(doc_pptx_create_tool())
                    ppt_template_id = _pptx_template_from_attachments(attachments)
                    if ppt_template_id:
                        messages.append(
                            ChatMessage(
                                role="system",
                                content=(
                                    "检测到用户上传了 PPTX 模板。"
                                    f" 生成时必须在 doc_pptx_create 参数中传 template_file_id='{ppt_template_id}'，并优先复用模板版式。"
                                ),
                            )
                        )
                if is_quote:
                    requested.append("quote")
                    messages.append(ChatMessage(role="system", content=_quote_system_instruction()))
                    tools.extend([doc_quote_xlsx_create_tool(), doc_quote_docx_create_tool()])
                if is_inspection:
                    requested.append("inspection")
                    messages.append(ChatMessage(role="system", content=_inspection_system_instruction(inspect_fmt or "docx")))
                    if inspect_fmt == "xlsx":
                        tools.append(doc_inspection_xlsx_create_tool())
                    else:
                        tools.append(doc_inspection_docx_create_tool())
                if is_proto:
                    requested.append("prototype")
                    messages.append(ChatMessage(role="system", content=_proto_system_instruction()))
                    tools.append(proto_generate_tool())

                tool_ctx = ToolContext(
                    session_id=sid,
                    workspace_root=workspace,
                    outputs_dir=self._settings.outputs_dir,
                    enable_shell=False,
                    enable_write=False,
                    enable_browser=False,
                    max_file_read_chars=self._settings.max_file_read_chars,
                    max_tool_output_chars=self._settings.max_tool_output_chars,
                    max_context_chars=max(0, int(self._settings.max_context_chars)),
                )

                messages.insert(
                    1,
                    ChatMessage(
                        role="system",
                        content=_runtime_system_prompt(provider="openai", model=used_model, workspace=workspace, tool_ctx=tool_ctx),
                    ),
                )

                provider_impl = OpenAiProvider(
                    api_key=self._settings.openai_api_key,
                    base_url=self._settings.openai_base_url,
                    outputs_dir=self._settings.outputs_dir,
                )

                events: list[dict[str, Any]] = [
                    {
                        "type": "security_profile",
                        "preset": security_profile,
                        "requested": {
                            "shell": requested_shell,
                            "write": requested_write,
                            "browser": requested_browser,
                            "dangerous": requested_dangerous,
                        },
                        "effective": {
                            "shell": False,
                            "write": False,
                            "browser": False,
                            "dangerous": False,
                        },
                    },
                    {"type": "codex_fallback", "provider": "openai", "requested": requested},
                ]

                async def on_event(ev):  # noqa: ANN001
                    events.append({"type": ev.type, **ev.data})

                assistant, _messages_out = await run_agent_task(
                    provider=provider_impl,
                    model=used_model,
                    messages=messages,
                    user_input=message,
                    user_attachments=attachments,
                    tools=tools,
                    tool_ctx=tool_ctx,
                    max_steps=max(1, int(self._settings.max_steps)),
                    on_event=on_event,
                )

                await store.update_messages(
                    session_id=sid,
                    user_id=user_id,
                    team_id=team_id,
                    messages=[
                        *session.messages,
                        ChatMessage(role="user", content=message, attachments=attachments or None),
                        ChatMessage(role="assistant", content=assistant),
                    ],
                    max_messages=max(0, int(self._settings.max_session_messages)),
                    max_chars=max(0, int(self._settings.max_context_chars)),
                )

                return {"session_id": sid, "assistant": assistant, "events": events, "opencode_session_id": None}

            effective_dangerous = requested_dangerous and bool(self._settings.codex_allow_dangerous)

            svc = CodexService(self._settings)

            result = await svc.chat(
                session=session,
                message=message,
                role=role,
                model=model,
                workspace_root=workspace,
                enable_shell=effective_shell,
                enable_write=effective_write,
                enable_browser=effective_browser,
                dangerous_bypass=effective_dangerous,
                system_prompt=extra_system or None,
                attachments=attachments,
            )

            await store.update_messages(
                session_id=sid,
                user_id=user_id,
                team_id=team_id,
                messages=[
                    *session.messages,
                    ChatMessage(role="user", content=message, attachments=attachments or None),
                    ChatMessage(role="assistant", content=result.assistant),
                ],
                max_messages=max(0, int(self._settings.max_session_messages)),
                max_chars=max(0, int(self._settings.max_context_chars)),
            )

            return {
                "session_id": sid,
                "assistant": result.assistant,
                "events": [
                    {
                        "type": "security_profile",
                        "preset": security_profile,
                        "requested": {
                            "shell": requested_shell,
                            "write": requested_write,
                            "browser": requested_browser,
                            "dangerous": requested_dangerous,
                        },
                        "effective": {
                            "shell": effective_shell,
                            "write": effective_write,
                            "browser": effective_browser,
                            "dangerous": effective_dangerous,
                        },
                    },
                    *result.events,
                ],
                "opencode_session_id": None,
            }

        if provider_name == "opencode":
            # Keep aistaff session ownership/TTL, but delegate the agent loop to OpenCode.
            session = await store.get_or_create(
                session_id=sid,
                user_id=user_id,
                team_id=team_id,
                role=role,
                system_prompt=f"opencode:{role}",
                workspace_root=str(workspace),
                ttl_seconds=max(0, int(self._settings.session_ttl_minutes)) * 60,
                max_sessions=max(0, int(self._settings.max_sessions)),
            )

            # For OpenCode, pass team skills as extra system instruction (avoid mentioning aistaff-specific tools).
            extra_system = ""
            if team_skills_prompt and team_skills_prompt.strip():
                extra_system = team_skills_prompt.strip()
            if summary_text:
                extra_system = f"{extra_system}\n\n{summary_text}" if extra_system else summary_text

            # OpenCode provider doesn't know aistaff's document/prototype tools. For doc/proto requests,
            # fall back to aistaff's own agent loop so users can trigger file generation via natural language.
            is_ppt, ppt_pages = _ppt_request(message)
            is_quote = _quote_request(message)
            inspect_fmt = _inspection_request(message)
            is_inspection = inspect_fmt is not None
            is_proto = _proto_request(message)
            has_attachments = bool(attachments)
            if is_ppt or is_quote or is_inspection or is_proto or has_attachments:
                # Fast-path: generate a draft quote XLSX directly when request is simple.
                if is_quote and not (is_ppt or is_inspection or is_proto) and not has_attachments:
                    items, missing = _parse_quote_items_from_message(message)
                    note = ""
                    if missing:
                        note = f"缺失项已用 0 占位，待补齐：{'；'.join(missing)}"

                    args = {
                        "seller": "某某科技有限公司",
                        "buyer": "某某客户",
                        "currency": "CNY",
                        "items": items,
                        "note": note or None,
                    }

                    tool_ctx = ToolContext(
                        session_id=sid,
                        workspace_root=workspace,
                        outputs_dir=self._settings.outputs_dir,
                        enable_shell=False,
                        enable_write=False,
                        enable_browser=False,
                        max_file_read_chars=self._settings.max_file_read_chars,
                        max_tool_output_chars=self._settings.max_tool_output_chars,
                        max_context_chars=max(0, int(self._settings.max_context_chars)),
                    )

                    tool = doc_quote_xlsx_create_tool()
                    parsed = tool.input_model.model_validate(args)
                    meta = await tool.handler(parsed, tool_ctx)

                    download_url = str(meta.get("download_url") or "").strip()
                    missing_lines = "\n".join([f"- {m}" for m in missing]) if missing else ""

                    if show_reasoning:
                        assistant = (
                            "Thoughts\n"
                            "- 已按清单生成报价单 Excel（缺失项用 0 占位）\n"
                            "- 待补齐字段已写入备注，便于你快速补齐\n"
                            "- 你补齐数量/单价后我可以立刻重生成正式报价\n\n"
                            "Answer\n"
                            f"已生成报价单 Excel（XLSX）。\n\n下载：{download_url or '（生成成功但未返回下载链接）'}"
                        ).strip()
                    else:
                        assistant = f"已生成报价单 Excel（XLSX）。\n\n下载：{download_url or '（生成成功但未返回下载链接）'}".strip()

                    if missing_lines:
                        assistant = f"{assistant}\n\n待补齐：\n{missing_lines}".strip()

                    events: list[dict[str, Any]] = [
                        {
                            "type": "security_profile",
                            "preset": security_profile,
                            "requested": {
                                "shell": requested_shell,
                                "write": requested_write,
                                "browser": requested_browser,
                            },
                            "effective": {
                                "shell": False,
                                "write": False,
                                "browser": False,
                            },
                        },
                        {"type": "opencode_fallback", "provider": "builtin", "requested": ["quote"]},
                        {"type": "tool_call", "tool": "doc_quote_xlsx_create", "args": args},
                        {"type": "tool_result", "tool": "doc_quote_xlsx_create", "result": meta},
                    ]

                    await store.update_messages(
                        session_id=sid,
                        user_id=user_id,
                        team_id=team_id,
                        messages=[
                            *session.messages,
                            ChatMessage(role="user", content=message),
                            ChatMessage(role="assistant", content=assistant),
                        ],
                        max_messages=max(0, int(self._settings.max_session_messages)),
                        max_chars=max(0, int(self._settings.max_context_chars)),
                    )

                    return {"session_id": sid, "assistant": assistant, "events": events, "opencode_session_id": None}

                system_prompt = await build_system_prompt(self._settings.app_root, workspace, role)
                messages: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
                if extra_system:
                    messages.append(ChatMessage(role="system", content=extra_system))
                used_model = model or self._settings.model
                requested: list[str] = []
                tools: list[ToolDefinition] = [fs_list_tool(), fs_read_tool(), attachment_read_tool()]
                if is_ppt:
                    requested.append("ppt")
                    messages.append(ChatMessage(role="system", content=_ppt_system_instruction(ppt_pages)))
                    tools.append(doc_pptx_create_tool())
                    ppt_template_id = _pptx_template_from_attachments(attachments)
                    if ppt_template_id:
                        messages.append(
                            ChatMessage(
                                role="system",
                                content=(
                                    "检测到用户上传了 PPTX 模板。"
                                    f" 生成时必须在 doc_pptx_create 参数中传 template_file_id='{ppt_template_id}'，并优先复用模板版式。"
                                ),
                            )
                        )
                if is_quote:
                    requested.append("quote")
                    messages.append(ChatMessage(role="system", content=_quote_system_instruction()))
                    tools.extend([doc_quote_xlsx_create_tool(), doc_quote_docx_create_tool()])
                if is_inspection:
                    requested.append("inspection")
                    messages.append(ChatMessage(role="system", content=_inspection_system_instruction(inspect_fmt or "docx")))
                    if inspect_fmt == "xlsx":
                        tools.append(doc_inspection_xlsx_create_tool())
                    else:
                        tools.append(doc_inspection_docx_create_tool())
                if is_proto:
                    requested.append("prototype")
                    messages.append(ChatMessage(role="system", content=_proto_system_instruction()))
                    tools.append(proto_generate_tool())

                tool_ctx = ToolContext(
                    session_id=sid,
                    workspace_root=workspace,
                    outputs_dir=self._settings.outputs_dir,
                    enable_shell=False,
                    enable_write=False,
                    enable_browser=False,
                    max_file_read_chars=self._settings.max_file_read_chars,
                    max_tool_output_chars=self._settings.max_tool_output_chars,
                    max_context_chars=max(0, int(self._settings.max_context_chars)),
                )

                # Add runtime info as a system message (kept near the top).
                messages.insert(
                    1,
                    ChatMessage(
                        role="system",
                        content=_runtime_system_prompt(provider="openai", model=used_model, workspace=workspace, tool_ctx=tool_ctx),
                    ),
                )

                provider_impl = OpenAiProvider(
                    api_key=self._settings.openai_api_key,
                    base_url=self._settings.openai_base_url,
                    outputs_dir=self._settings.outputs_dir,
                )

                events: list[dict[str, Any]] = [
                    {
                        "type": "security_profile",
                        "preset": security_profile,
                        "requested": {
                            "shell": requested_shell,
                            "write": requested_write,
                            "browser": requested_browser,
                        },
                        "effective": {
                            "shell": False,
                            "write": False,
                            "browser": False,
                        },
                    },
                    {"type": "opencode_fallback", "provider": "openai", "requested": requested},
                ]

                async def on_event(ev):  # noqa: ANN001
                    events.append({"type": ev.type, **ev.data})

                assistant, _messages_out = await run_agent_task(
                    provider=provider_impl,
                    model=used_model,
                    messages=messages,
                    user_input=message,
                    user_attachments=attachments,
                    tools=tools,
                    tool_ctx=tool_ctx,
                    max_steps=max(1, int(self._settings.max_steps)),
                    on_event=on_event,
                )

                await store.update_messages(
                    session_id=sid,
                    user_id=user_id,
                    team_id=team_id,
                    messages=[
                        *session.messages,
                        ChatMessage(role="user", content=message),
                        ChatMessage(role="assistant", content=assistant),
                    ],
                    max_messages=max(0, int(self._settings.max_session_messages)),
                    max_chars=max(0, int(self._settings.max_context_chars)),
                )

                return {"session_id": sid, "assistant": assistant, "events": events, "opencode_session_id": None}

            svc = OpencodeService(self._settings)
            opencode_agent = "build" if role == "engineer" else "general"
            # If no model is specified per-request, let OpenCode decide (via opencode.jsonc / server defaults).
            used_model = model
            result = await svc.chat(
                session=session,
                message=message,
                agent=opencode_agent,
                model=used_model,
                workspace_root=workspace,
                enable_shell=effective_shell,
                enable_write=effective_write,
                system_prompt=extra_system or None,
            )

            # Store minimal chat history for session bookkeeping.
            await store.update_messages(
                session_id=sid,
                user_id=user_id,
                team_id=team_id,
                messages=[
                    *session.messages,
                    ChatMessage(role="user", content=message),
                    ChatMessage(role="assistant", content=result.assistant),
                ],
                max_messages=max(0, int(self._settings.max_session_messages)),
                max_chars=max(0, int(self._settings.max_context_chars)),
            )

            return {
                "session_id": sid,
                "assistant": result.assistant,
                "events": [
                    {
                        "type": "security_profile",
                        "preset": security_profile,
                        "requested": {
                            "shell": requested_shell,
                            "write": requested_write,
                            "browser": requested_browser,
                        },
                        "effective": {
                            "shell": effective_shell,
                            "write": effective_write,
                            "browser": effective_browser,
                        },
                    },
                    *result.events,
                ],
                "opencode_session_id": session.opencode_session_id,
            }

        if provider_name == "pi":
            if not bool(getattr(self._settings, "enable_pi", False)):
                raise ValueError("Pi provider is disabled. Set AISTAFF_ENABLE_PI=1 to enable it.")

            session = await store.get_or_create(
                session_id=sid,
                user_id=user_id,
                team_id=team_id,
                role=role,
                system_prompt=f"pi:{role}",
                workspace_root=str(workspace),
                ttl_seconds=max(0, int(self._settings.session_ttl_minutes)) * 60,
                max_sessions=max(0, int(self._settings.max_sessions)),
            )

            extra_system = ""
            if team_skills_prompt and team_skills_prompt.strip():
                extra_system = team_skills_prompt.strip()
            if summary_text:
                extra_system = f"{extra_system}\n\n{summary_text}" if extra_system else summary_text

            is_ppt, ppt_pages = _ppt_request(message)
            is_quote = _quote_request(message)
            inspect_fmt = _inspection_request(message)
            is_inspection = inspect_fmt is not None
            is_proto = _proto_request(message)
            has_attachments = bool(attachments)

            # Pi doesn't know aistaff's artifact tools; fall back to aistaff agent loop for doc/proto/attachments.
            if is_ppt or is_quote or is_inspection or is_proto or has_attachments:
                requested = []
                if is_ppt:
                    requested.append("ppt")
                if is_quote:
                    requested.append("quote")
                if is_inspection:
                    requested.append("inspection")
                if is_proto:
                    requested.append("proto")
                if has_attachments:
                    requested.append("attachments")

                extra_preset = self._normalize_security_preset(security_preset)
                requested_shell2, requested_write2, requested_browser2 = self._resolve_security_toggles(
                    preset=extra_preset,
                    enable_shell=None,
                    enable_write=None,
                    enable_browser=None,
                )
                tool_ctx = ToolContext(
                    session_id=sid,
                    workspace_root=workspace,
                    outputs_dir=self._settings.outputs_dir,
                    enable_shell=False,
                    enable_write=False,
                    enable_browser=False,
                    max_file_read_chars=self._settings.max_file_read_chars,
                    max_tool_output_chars=self._settings.max_tool_output_chars,
                    max_context_chars=max(0, int(self._settings.max_context_chars)),
                )

                tools = self._build_tools(tool_ctx)
                used_model = (model or self._settings.model or "gpt-5.2").strip() or "gpt-5.2"
                provider_impl = OpenAiProvider(
                    api_key=self._settings.openai_api_key,
                    base_url=self._settings.openai_base_url,
                    outputs_dir=self._settings.outputs_dir,
                )

                messages: list[ChatMessage] = list(session.messages)
                extra_system_text = extra_system.strip() if extra_system else ""
                if is_ppt:
                    extra_system_text = f"{extra_system_text}\n\n{_ppt_system_instruction(ppt_pages)}".strip()
                if is_quote:
                    extra_system_text = f"{extra_system_text}\n\n{_quote_system_instruction()}".strip()
                if is_inspection:
                    extra_system_text = f"{extra_system_text}\n\n{_inspection_system_instruction(inspect_fmt or 'docx')}".strip()
                if is_proto:
                    extra_system_text = f"{extra_system_text}\n\n{_proto_system_instruction()}".strip()

                if extra_system_text:
                    messages.append(ChatMessage(role="system", content=extra_system_text))

                events: list[dict[str, Any]] = [
                    {
                        "type": "security_profile",
                        "preset": security_profile,
                        "requested": {
                            "shell": requested_shell2,
                            "write": requested_write2,
                            "browser": requested_browser2,
                            "dangerous": bool(enable_dangerous),
                        },
                        "effective": {
                            "shell": False,
                            "write": False,
                            "browser": False,
                            "dangerous": False,
                        },
                    },
                    {"type": "pi_fallback", "provider": "openai", "requested": requested},
                ]

                async def on_event(ev):  # noqa: ANN001
                    events.append({"type": ev.type, **ev.data})

                assistant, _messages_out = await run_agent_task(
                    provider=provider_impl,
                    model=used_model,
                    messages=messages,
                    user_input=message,
                    user_attachments=attachments,
                    tools=tools,
                    tool_ctx=tool_ctx,
                    max_steps=max(1, int(self._settings.max_steps)),
                    on_event=on_event,
                )

                await store.update_messages(
                    session_id=sid,
                    user_id=user_id,
                    team_id=team_id,
                    messages=[
                        *session.messages,
                        ChatMessage(role="user", content=message, attachments=attachments or None),
                        ChatMessage(role="assistant", content=assistant),
                    ],
                    max_messages=max(0, int(self._settings.max_session_messages)),
                    max_chars=max(0, int(self._settings.max_context_chars)),
                )

                return {"session_id": sid, "assistant": assistant, "events": events, "opencode_session_id": None}

            svc = PiService(self._settings)
            used_model = model
            result = await svc.chat(
                session=session,
                message=message,
                role=role,
                model=used_model,
                workspace_root=workspace,
                enable_shell=effective_shell,
                enable_write=effective_write,
                system_prompt=extra_system or None,
            )

            await store.update_messages(
                session_id=sid,
                user_id=user_id,
                team_id=team_id,
                messages=[
                    *session.messages,
                    ChatMessage(role="user", content=message, attachments=attachments or None),
                    ChatMessage(role="assistant", content=result.assistant),
                ],
                max_messages=max(0, int(self._settings.max_session_messages)),
                max_chars=max(0, int(self._settings.max_context_chars)),
            )

            return {
                "session_id": sid,
                "assistant": result.assistant,
                "events": [
                    {
                        "type": "security_profile",
                        "preset": security_profile,
                        "requested": {
                            "shell": requested_shell,
                            "write": requested_write,
                            "browser": requested_browser,
                        },
                        "effective": {
                            "shell": effective_shell,
                            "write": effective_write,
                            "browser": effective_browser,
                        },
                    },
                    *result.events,
                ],
                "opencode_session_id": None,
            }

        if provider_name == "nanobot":
            # Keep aistaff session ownership/TTL, but delegate the agent loop to Nanobot.
            session = await store.get_or_create(
                session_id=sid,
                user_id=user_id,
                team_id=team_id,
                role=role,
                system_prompt=f"nanobot:{role}",
                workspace_root=str(workspace),
                ttl_seconds=max(0, int(self._settings.session_ttl_minutes)) * 60,
                max_sessions=max(0, int(self._settings.max_sessions)),
            )

            # For Nanobot, pass team skills as extra system instruction (avoid mentioning aistaff-specific tools).
            extra_system = ""
            if team_skills_prompt and team_skills_prompt.strip():
                extra_system = team_skills_prompt.strip()
            if summary_text:
                extra_system = f"{extra_system}\n\n{summary_text}" if extra_system else summary_text

            # Nanobot provider doesn't know aistaff's document/prototype/attachment tools.
            # For these scenarios, fall back to aistaff's own agent loop.
            is_ppt, ppt_pages = _ppt_request(message)
            is_quote = _quote_request(message)
            inspect_fmt = _inspection_request(message)
            is_inspection = inspect_fmt is not None
            is_proto = _proto_request(message)
            has_attachments = bool(attachments)
            if is_ppt or is_quote or is_inspection or is_proto or has_attachments:
                # Fast-path: generate a draft quote XLSX directly when request is simple.
                if is_quote and not (is_ppt or is_inspection or is_proto) and not has_attachments:
                    items, missing = _parse_quote_items_from_message(message)
                    note = ""
                    if missing:
                        note = f"缺失项已用 0 占位，待补齐：{'；'.join(missing)}"

                    args = {
                        "seller": "某某科技有限公司",
                        "buyer": "某某客户",
                        "currency": "CNY",
                        "items": items,
                        "note": note or None,
                    }

                    tool_ctx = ToolContext(
                        session_id=sid,
                        workspace_root=workspace,
                        outputs_dir=self._settings.outputs_dir,
                        enable_shell=False,
                        enable_write=False,
                        enable_browser=False,
                        max_file_read_chars=self._settings.max_file_read_chars,
                        max_tool_output_chars=self._settings.max_tool_output_chars,
                        max_context_chars=max(0, int(self._settings.max_context_chars)),
                    )

                    tool = doc_quote_xlsx_create_tool()
                    parsed = tool.input_model.model_validate(args)
                    meta = await tool.handler(parsed, tool_ctx)

                    download_url = str(meta.get("download_url") or "").strip()
                    missing_lines = "\n".join([f"- {m}" for m in missing]) if missing else ""

                    if show_reasoning:
                        assistant = (
                            "Thoughts\n"
                            "- 已按清单生成报价单 Excel（缺失项用 0 占位）\n"
                            "- 待补齐字段已写入备注，便于你快速补齐\n"
                            "- 你补齐数量/单价后我可以立刻重生成正式报价\n\n"
                            "Answer\n"
                            f"已生成报价单 Excel（XLSX）。\n\n下载：{download_url or '（生成成功但未返回下载链接）'}"
                        ).strip()
                    else:
                        assistant = f"已生成报价单 Excel（XLSX）。\n\n下载：{download_url or '（生成成功但未返回下载链接）'}".strip()

                    if missing_lines:
                        assistant = f"{assistant}\n\n待补齐：\n{missing_lines}".strip()

                    events: list[dict[str, Any]] = [
                        {
                            "type": "security_profile",
                            "preset": security_profile,
                            "requested": {
                                "shell": requested_shell,
                                "write": requested_write,
                                "browser": requested_browser,
                            },
                            "effective": {
                                "shell": False,
                                "write": False,
                                "browser": False,
                            },
                        },
                        {"type": "nanobot_fallback", "provider": "builtin", "requested": ["quote"]},
                        {"type": "tool_call", "tool": "doc_quote_xlsx_create", "args": args},
                        {"type": "tool_result", "tool": "doc_quote_xlsx_create", "result": meta},
                    ]

                    await store.update_messages(
                        session_id=sid,
                        user_id=user_id,
                        team_id=team_id,
                        messages=[
                            *session.messages,
                            ChatMessage(role="user", content=message),
                            ChatMessage(role="assistant", content=assistant),
                        ],
                        max_messages=max(0, int(self._settings.max_session_messages)),
                        max_chars=max(0, int(self._settings.max_context_chars)),
                    )

                    return {"session_id": sid, "assistant": assistant, "events": events, "opencode_session_id": None}

                system_prompt = await build_system_prompt(self._settings.app_root, workspace, role)
                messages: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
                if extra_system:
                    messages.append(ChatMessage(role="system", content=extra_system))
                used_model = model or self._settings.model
                requested: list[str] = []
                tools: list[ToolDefinition] = [fs_list_tool(), fs_read_tool(), attachment_read_tool()]
                if is_ppt:
                    requested.append("ppt")
                    messages.append(ChatMessage(role="system", content=_ppt_system_instruction(ppt_pages)))
                    tools.append(doc_pptx_create_tool())
                    ppt_template_id = _pptx_template_from_attachments(attachments)
                    if ppt_template_id:
                        messages.append(
                            ChatMessage(
                                role="system",
                                content=(
                                    "检测到用户上传了 PPTX 模板。"
                                    f" 生成时必须在 doc_pptx_create 参数中传 template_file_id='{ppt_template_id}'，并优先复用模板版式。"
                                ),
                            )
                        )
                if is_quote:
                    requested.append("quote")
                    messages.append(ChatMessage(role="system", content=_quote_system_instruction()))
                    tools.extend([doc_quote_xlsx_create_tool(), doc_quote_docx_create_tool()])
                if is_inspection:
                    requested.append("inspection")
                    messages.append(ChatMessage(role="system", content=_inspection_system_instruction(inspect_fmt or "docx")))
                    if inspect_fmt == "xlsx":
                        tools.append(doc_inspection_xlsx_create_tool())
                    else:
                        tools.append(doc_inspection_docx_create_tool())
                if is_proto:
                    requested.append("prototype")
                    messages.append(ChatMessage(role="system", content=_proto_system_instruction()))
                    tools.append(proto_generate_tool())

                tool_ctx = ToolContext(
                    session_id=sid,
                    workspace_root=workspace,
                    outputs_dir=self._settings.outputs_dir,
                    enable_shell=False,
                    enable_write=False,
                    enable_browser=False,
                    max_file_read_chars=self._settings.max_file_read_chars,
                    max_tool_output_chars=self._settings.max_tool_output_chars,
                    max_context_chars=max(0, int(self._settings.max_context_chars)),
                )

                # Add runtime info as a system message (kept near the top).
                messages.insert(
                    1,
                    ChatMessage(
                        role="system",
                        content=_runtime_system_prompt(provider="openai", model=used_model, workspace=workspace, tool_ctx=tool_ctx),
                    ),
                )

                provider_impl = OpenAiProvider(
                    api_key=self._settings.openai_api_key,
                    base_url=self._settings.openai_base_url,
                    outputs_dir=self._settings.outputs_dir,
                )

                events: list[dict[str, Any]] = [
                    {
                        "type": "security_profile",
                        "preset": security_profile,
                        "requested": {
                            "shell": requested_shell,
                            "write": requested_write,
                            "browser": requested_browser,
                        },
                        "effective": {
                            "shell": False,
                            "write": False,
                            "browser": False,
                        },
                    },
                    {"type": "nanobot_fallback", "provider": "openai", "requested": requested},
                ]

                async def on_event(ev):  # noqa: ANN001
                    events.append({"type": ev.type, **ev.data})

                assistant, _messages_out = await run_agent_task(
                    provider=provider_impl,
                    model=used_model,
                    messages=messages,
                    user_input=message,
                    user_attachments=attachments,
                    tools=tools,
                    tool_ctx=tool_ctx,
                    max_steps=max(1, int(self._settings.max_steps)),
                    on_event=on_event,
                )

                await store.update_messages(
                    session_id=sid,
                    user_id=user_id,
                    team_id=team_id,
                    messages=[
                        *session.messages,
                        ChatMessage(role="user", content=message),
                        ChatMessage(role="assistant", content=assistant),
                    ],
                    max_messages=max(0, int(self._settings.max_session_messages)),
                    max_chars=max(0, int(self._settings.max_context_chars)),
                )

                return {"session_id": sid, "assistant": assistant, "events": events, "opencode_session_id": None}

            svc = NanobotService(self._settings)
            # If no model is specified per-request, Nanobot will use AISTAFF_MODEL.
            result = await svc.chat(
                session=session,
                message=message,
                role=role,
                model=model,
                workspace_root=workspace,
                enable_shell=effective_shell,
                enable_write=effective_write,
                system_prompt=extra_system or None,
            )

            # Store minimal chat history for session bookkeeping.
            await store.update_messages(
                session_id=sid,
                user_id=user_id,
                team_id=team_id,
                messages=[
                    *session.messages,
                    ChatMessage(role="user", content=message),
                    ChatMessage(role="assistant", content=result.assistant),
                ],
                max_messages=max(0, int(self._settings.max_session_messages)),
                max_chars=max(0, int(self._settings.max_context_chars)),
            )

            return {
                "session_id": sid,
                "assistant": result.assistant,
                "events": [
                    {
                        "type": "security_profile",
                        "preset": security_profile,
                        "requested": {
                            "shell": requested_shell,
                            "write": requested_write,
                            "browser": requested_browser,
                        },
                        "effective": {
                            "shell": effective_shell,
                            "write": effective_write,
                            "browser": effective_browser,
                        },
                    },
                    *result.events,
                ],
                "opencode_session_id": None,
            }

        system_prompt = await build_system_prompt(self._settings.app_root, workspace, role)
        session = await store.get_or_create(
            session_id=sid,
            user_id=user_id,
            team_id=team_id,
            role=role,
            system_prompt=system_prompt,
            workspace_root=str(workspace),
            ttl_seconds=max(0, int(self._settings.session_ttl_minutes)) * 60,
            max_sessions=max(0, int(self._settings.max_sessions)),
        )

        # upsert/remove team skills system message (keep it near the top)
        team_text = (team_skills_prompt or "").strip()
        idx = None
        for i, m in enumerate(session.messages):
            if m.role == "system" and (m.content or "").startswith(_TEAM_SKILLS_MARKER):
                idx = i
                break
        if team_text:
            content = f"{_TEAM_SKILLS_MARKER}\n{team_text}"
            if idx is None:
                insert_at = 1 if session.messages and session.messages[0].role == "system" else 0
                session.messages.insert(insert_at, ChatMessage(role="system", content=content))
            else:
                session.messages[idx].content = content
        elif idx is not None:
            session.messages.pop(idx)

        # upsert/remove reasoning summary system message (keep it near the top)
        sidx = None
        for i, m in enumerate(session.messages):
            if m.role == "system" and (m.content or "").startswith(_SUMMARY_MARKER):
                sidx = i
                break
        if summary_text:
            if sidx is None:
                insert_at = 1 if session.messages and session.messages[0].role == "system" else 0
                session.messages.insert(insert_at, ChatMessage(role="system", content=summary_text))
            else:
                session.messages[sidx].content = summary_text
        elif sidx is not None:
            session.messages.pop(sidx)

        tool_ctx = ToolContext(
            session_id=sid,
            workspace_root=workspace,
            outputs_dir=self._settings.outputs_dir,
            enable_shell=effective_shell,
            enable_write=effective_write,
            enable_browser=effective_browser,
            max_file_read_chars=self._settings.max_file_read_chars,
            max_tool_output_chars=self._settings.max_tool_output_chars,
            max_context_chars=max(0, int(self._settings.max_context_chars)),
        )

        used_model = model or self._settings.model

        # upsert runtime system message (keep it near the top)
        runtime = _runtime_system_prompt(
            provider=provider_name,
            model=str(used_model),
            workspace=workspace,
            tool_ctx=tool_ctx,
        )
        ridx = None
        for i, m in enumerate(session.messages):
            if m.role == "system" and (m.content or "").startswith(_RUNTIME_MARKER):
                ridx = i
                break
        if ridx is None:
            insert_at = 1 if session.messages and session.messages[0].role == "system" else 0
            session.messages.insert(insert_at, ChatMessage(role="system", content=runtime))
        else:
            session.messages[ridx].content = runtime

        tools = self._build_tools(tool_ctx)
        provider_impl = self._get_provider(provider)

        events: list[dict[str, Any]] = [
            {
                "type": "security_profile",
                "preset": security_profile,
                "requested": {
                    "shell": requested_shell,
                    "write": requested_write,
                    "browser": requested_browser,
                },
                "effective": {
                    "shell": effective_shell,
                    "write": effective_write,
                    "browser": effective_browser,
                },
            }
        ]

        async def on_event(ev):  # noqa: ANN001
            events.append({"type": ev.type, **ev.data})

        is_ppt, ppt_pages = _ppt_request(message)
        is_quote = _quote_request(message)
        inspect_fmt = _inspection_request(message)
        is_inspection = inspect_fmt is not None
        is_proto = _proto_request(message)

        # Fast-path: generate a draft quote XLSX directly when request is simple (no attachments).
        # This avoids blocking the user with clarification questions.
        if is_quote and not (is_ppt or is_inspection or is_proto) and not attachments:
            items, missing = _parse_quote_items_from_message(message)
            note = ""
            if missing:
                note = f"缺失项已用 0 占位，待补齐：{'；'.join(missing)}"

            args = {
                "seller": "某某科技有限公司",
                "buyer": "某某客户",
                "currency": "CNY",
                "items": items,
                "note": note or None,
            }

            tool = doc_quote_xlsx_create_tool()
            parsed = tool.input_model.model_validate(args)
            meta = await tool.handler(parsed, tool_ctx)
            events.extend(
                [
                    {"type": "tool_call", "tool": "doc_quote_xlsx_create", "args": args},
                    {"type": "tool_result", "tool": "doc_quote_xlsx_create", "result": meta},
                ]
            )

            download_url = str(meta.get("download_url") or "").strip()
            missing_lines = "\n".join([f"- {m}" for m in missing]) if missing else ""

            if show_reasoning:
                assistant = (
                    "Thoughts\n"
                    "- 已按清单生成报价单 Excel（缺失项用 0 占位）\n"
                    "- 待补齐字段已写入备注，便于你快速补齐\n"
                    "- 你补齐数量/单价后我可以立刻重生成正式报价\n\n"
                    "Answer\n"
                    f"已生成报价单 Excel（XLSX）。\n\n下载：{download_url or '（生成成功但未返回下载链接）'}"
                ).strip()
            else:
                assistant = f"已生成报价单 Excel（XLSX）。\n\n下载：{download_url or '（生成成功但未返回下载链接）'}".strip()

            if missing_lines:
                assistant = f"{assistant}\n\n待补齐：\n{missing_lines}".strip()

            await store.update_messages(
                session_id=sid,
                user_id=user_id,
                team_id=team_id,
                messages=[
                    *session.messages,
                    ChatMessage(role="user", content=message, attachments=attachments or None),
                    ChatMessage(role="assistant", content=assistant),
                ],
                max_messages=max(0, int(self._settings.max_session_messages)),
                max_chars=max(0, int(self._settings.max_context_chars)),
            )

            return {"session_id": sid, "assistant": assistant, "events": events, "opencode_session_id": None}

        run_messages = session.messages
        mode_markers: list[str] = []
        if is_ppt:
            mode_markers.append(_PPT_MODE_MARKER)
            run_messages = [*run_messages, ChatMessage(role="system", content=_ppt_system_instruction(ppt_pages))]
            ppt_template_id = _pptx_template_from_attachments(attachments)
            if ppt_template_id:
                run_messages = [
                    *run_messages,
                    ChatMessage(
                        role="system",
                        content=(
                            "检测到用户上传了 PPTX 模板。"
                            f" 生成时必须在 doc_pptx_create 参数中传 template_file_id='{ppt_template_id}'，并优先复用模板版式。"
                        ),
                    ),
                ]
        if is_quote:
            mode_markers.append(_QUOTE_MODE_MARKER)
            run_messages = [*run_messages, ChatMessage(role="system", content=_quote_system_instruction())]
        if is_inspection:
            mode_markers.append(_INSPECTION_MODE_MARKER)
            run_messages = [*run_messages, ChatMessage(role="system", content=_inspection_system_instruction(inspect_fmt or "docx"))]
        if is_proto:
            mode_markers.append(_PROTO_MODE_MARKER)
            run_messages = [*run_messages, ChatMessage(role="system", content=_proto_system_instruction())]

        assistant, messages = await run_agent_task(
            provider=provider_impl,
            model=used_model,
            messages=run_messages,
            user_input=message,
            user_attachments=attachments,
            tools=tools,
            tool_ctx=tool_ctx,
            max_steps=self._settings.max_steps,
            on_event=on_event,
        )

        if mode_markers:
            messages = [
                m
                for m in messages
                if not (m.role == "system" and any((m.content or "").strip().startswith(mm) for mm in mode_markers))
            ]

        await store.update_messages(
            session_id=sid,
            user_id=user_id,
            team_id=team_id,
            messages=messages,
            max_messages=max(0, int(self._settings.max_session_messages)),
            max_chars=max(0, int(self._settings.max_context_chars)),
        )
        return {"session_id": sid, "assistant": assistant, "events": events, "opencode_session_id": None}
