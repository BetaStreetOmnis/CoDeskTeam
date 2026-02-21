import type { ModelProvider } from "../llm/types.js"
import type { ToolContext, ToolDefinition } from "../tools/types.js"
import { safeJsonStringify, truncate } from "../util/text.js"
import type { AgentEvent, ChatMessage } from "./types.js"

export async function runAgentTask(params: {
  provider: ModelProvider
  model: string
  messages: ChatMessage[]
  userInput: string
  tools: ToolDefinition[]
  toolContext: ToolContext
  maxSteps: number
  onEvent?: (event: AgentEvent) => void
}): Promise<{ finalText: string; messages: ChatMessage[] }> {
  const messages: ChatMessage[] = [...params.messages, { role: "user", content: params.userInput }]

  const toolByName = new Map<string, ToolDefinition>(params.tools.map((t) => [t.name, t]))

  for (let step = 0; step < params.maxSteps; step += 1) {
    const response = await params.provider.complete({
      model: params.model,
      messages,
      tools: params.tools,
    })

    if (response.toolCalls.length > 0) {
      messages.push({ role: "assistant", toolCalls: response.toolCalls })

      for (const call of response.toolCalls) {
        const tool = toolByName.get(call.name)
        if (!tool) {
          const err = `Unknown tool: ${call.name}`
          params.onEvent?.({ type: "error", message: err })
          messages.push({ role: "tool", toolCallId: call.id, name: call.name, content: err })
          continue
        }

        let parsedArgs: unknown
        try {
          parsedArgs = JSON.parse(call.argsJson || "{}")
        } catch (e) {
          const err = `Invalid JSON arguments for tool ${call.name}: ${String(e)}`
          params.onEvent?.({ type: "error", message: err })
          messages.push({ role: "tool", toolCallId: call.id, name: call.name, content: err })
          continue
        }

        params.onEvent?.({ type: "tool_call", toolName: call.name, args: parsedArgs })

        try {
          const input = tool.inputSchema.parse(parsedArgs)
          const result = await tool.handler(input, params.toolContext)
          params.onEvent?.({ type: "tool_result", toolName: call.name, result })

          const content = truncate(safeJsonStringify(result), params.toolContext.maxToolOutputChars)
          messages.push({ role: "tool", toolCallId: call.id, name: call.name, content })
        } catch (e) {
          const err = `Tool ${call.name} failed: ${String(e)}`
          params.onEvent?.({ type: "error", message: err })
          messages.push({ role: "tool", toolCallId: call.id, name: call.name, content: err })
        }
      }

      continue
    }

    const assistantText = (response.assistantText ?? "").trim()
    messages.push({ role: "assistant", content: assistantText })
    params.onEvent?.({ type: "assistant_message", content: assistantText })
    return { finalText: assistantText, messages }
  }

  const errText = `Stopped after maxSteps=${params.maxSteps}.`
  params.onEvent?.({ type: "error", message: errText })
  return { finalText: errText, messages }
}
