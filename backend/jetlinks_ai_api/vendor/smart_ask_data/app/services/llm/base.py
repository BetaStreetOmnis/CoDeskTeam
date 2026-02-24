from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    async def chat(self, question: str, history: list[dict]) -> str:
        raise NotImplementedError

    async def explain_sql(self, question: str, sql: str) -> str:
        raise NotImplementedError

    async def generate_sql(self, prompt: str) -> str:
        raise NotImplementedError

    async def classify_intent(self, question: str, history: list[dict]) -> str:
        raise NotImplementedError
