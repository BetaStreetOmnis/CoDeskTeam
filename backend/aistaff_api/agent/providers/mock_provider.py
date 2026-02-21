from __future__ import annotations

from .base import ModelProvider, ModelResponse


class MockProvider(ModelProvider):
    name = "mock"

    async def complete(self, *, model: str, messages, tools) -> ModelResponse:  # noqa: ANN001
        _ = (model, messages, tools)
        return ModelResponse(
            assistant_text="（mock 模型）我已启动。要真正生成文档/写代码/浏览器操作，请配置 OPENAI_API_KEY 并使用 openai provider。",
            tool_calls=[],
        )

