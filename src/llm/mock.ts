import type { ModelCompleteRequest, ModelProvider, ModelResponse } from "./types.js"

export class MockProvider implements ModelProvider {
  public readonly name = "mock"

  public async complete(_request: ModelCompleteRequest): Promise<ModelResponse> {
    return {
      assistantText:
        "（mock 模型）我已经启动。要真正调用工具/联网/写代码，请设置 OPENAI_API_KEY 并使用 --provider openai。",
      toolCalls: [],
    }
  }
}

