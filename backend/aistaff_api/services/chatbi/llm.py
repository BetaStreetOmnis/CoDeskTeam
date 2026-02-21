from __future__ import annotations

from dataclasses import dataclass

from ...agent.providers.openai_provider import OpenAiProvider
from ...agent.types import ChatMessage


@dataclass(frozen=True)
class ChatbiLlmConfig:
    base_url: str
    api_key: str | None
    model: str


class ChatbiLLM:
    def __init__(self, cfg: ChatbiLlmConfig) -> None:
        self._cfg = cfg
        self._provider = OpenAiProvider(api_key=cfg.api_key, base_url=cfg.base_url)

    async def complete_text(self, *, system: str, user: str) -> str:
        res = await self._provider.complete(
            model=self._cfg.model,
            messages=[
                ChatMessage(role="system", content=system),
                ChatMessage(role="user", content=user),
            ],
            tools=[],
        )
        return (res.assistant_text or "").strip()

    async def generate_sql(self, *, prompt: str) -> str:
        system = (
            "你是一个严谨的数据分析助手。你必须只输出 SQL（不要输出解释、不要输出 Markdown）。"
        )
        return await self.complete_text(system=system, user=prompt)

    async def explain_sql(self, *, question: str, sql: str) -> str:
        system = "你是一个严谨的数据分析助手。请用中文解释 SQL 的意图与关键字段。"
        user = (
            "请解释下面这条 SQL：\n\n"
            f"问题：{question}\n\n"
            f"SQL：\n{sql}\n\n"
            "要求：\n"
            "- 说明这条 SQL 在查什么、按什么维度统计、用了哪些过滤条件\n"
            "- 列出输出字段含义（如可推断）\n"
            "- 不要虚构不存在的字段或表\n"
        )
        return await self.complete_text(system=system, user=user)
