export type ToolCall = {
  id: string
  name: string
  argsJson: string
}

export type ChatMessage =
  | { role: "system"; content: string }
  | { role: "user"; content: string }
  | { role: "assistant"; content?: string; toolCalls?: ToolCall[] }
  | { role: "tool"; toolCallId: string; name: string; content: string }

export type AgentEvent =
  | { type: "tool_call"; toolName: string; args: unknown }
  | { type: "tool_result"; toolName: string; result: unknown }
  | { type: "assistant_message"; content: string }
  | { type: "error"; message: string }

