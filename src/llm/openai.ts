import type { ChatMessage, ToolCall } from "../agent/types.js"
import type { ToolDefinition } from "../tools/types.js"
import type { ModelCompleteRequest, ModelProvider, ModelResponse } from "./types.js"

type OpenAiTool = {
  type: "function"
  function: {
    name: string
    description?: string
    parameters?: Record<string, unknown>
  }
}

type OpenAiMessage =
  | { role: "system"; content: string }
  | { role: "user"; content: string }
  | {
      role: "assistant"
      content: string | null
      tool_calls?: Array<{
        id: string
        type: "function"
        function: { name: string; arguments: string }
      }>
    }
  | { role: "tool"; tool_call_id: string; content: string }

function toOpenAiTools(tools: ToolDefinition[]): OpenAiTool[] {
  return tools.map((t) => ({
    type: "function",
    function: {
      name: t.name,
      description: t.description,
      parameters: t.parametersJsonSchema,
    },
  }))
}

function toOpenAiMessages(messages: ChatMessage[]): OpenAiMessage[] {
  return messages.map((m) => {
    if (m.role === "system") return { role: "system", content: m.content }
    if (m.role === "user") return { role: "user", content: m.content }
    if (m.role === "tool") return { role: "tool", tool_call_id: m.toolCallId, content: m.content }
    return {
      role: "assistant",
      content: m.content ?? null,
      tool_calls: m.toolCalls?.map((tc) => ({
        id: tc.id,
        type: "function",
        function: { name: tc.name, arguments: tc.argsJson },
      })),
    }
  })
}

export class OpenAiProvider implements ModelProvider {
  public readonly name = "openai"

  public constructor(private readonly apiKey: string, private readonly baseUrl = "https://api.openai.com/v1") {}

  public async complete(request: ModelCompleteRequest): Promise<ModelResponse> {
    const body = {
      model: request.model,
      messages: toOpenAiMessages(request.messages),
      tools: toOpenAiTools(request.tools),
      tool_choice: "auto",
    }

    const res = await fetch(`${this.baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    })

    const raw = await res.text()
    if (!res.ok) {
      throw new Error(`OpenAI error ${res.status}: ${raw}`)
    }

    const data = JSON.parse(raw) as {
      choices?: Array<{
        message?: { content?: string | null; tool_calls?: Array<{ id: string; function: { name: string; arguments: string } }> }
      }>
    }

    const message = data.choices?.[0]?.message
    const assistantText = message?.content ?? null
    const toolCalls: ToolCall[] = (message?.tool_calls ?? []).map((tc) => ({
      id: tc.id,
      name: tc.function.name,
      argsJson: tc.function.arguments,
    }))

    return { assistantText, toolCalls }
  }
}

