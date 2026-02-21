import type { ToolDefinition } from "../tools/types.js"
import type { ChatMessage, ToolCall } from "../agent/types.js"

export type ModelResponse = {
  assistantText: string | null
  toolCalls: ToolCall[]
}

export type ModelCompleteRequest = {
  model: string
  messages: ChatMessage[]
  tools: ToolDefinition[]
}

export interface ModelProvider {
  readonly name: string
  complete(request: ModelCompleteRequest): Promise<ModelResponse>
}

