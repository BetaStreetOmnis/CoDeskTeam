import http from "node:http"
import { WebSocketServer } from "ws"
import { buildSystemPrompt } from "../agent/prompt.js"
import { runAgentTask } from "../agent/run-task.js"
import type { ChatMessage } from "../agent/types.js"
import type { AiStaffConfig } from "../config.js"
import { createBuiltInTools } from "../tools/index.js"
import type { ToolContext } from "../tools/types.js"
import type { ModelProvider } from "../llm/types.js"
import { ulid } from "ulid"

type ClientToServer =
  | { type: "user_message"; content: string }
  | { type: "ping" }

type ServerToClient =
  | { type: "welcome"; sessionId: string }
  | { type: "pong" }
  | { type: "tool_call"; toolName: string; args: unknown }
  | { type: "tool_result"; toolName: string; result: unknown }
  | { type: "assistant_message"; content: string }
  | { type: "error"; message: string }

export async function startGateway(params: {
  config: AiStaffConfig
  provider: ModelProvider
  role: string
}): Promise<http.Server> {
  const server = http.createServer((req, res) => {
    if (req.method === "GET" && req.url === "/health") {
      res.writeHead(200, { "content-type": "application/json" })
      res.end(JSON.stringify({ ok: true }))
      return
    }
    res.writeHead(404, { "content-type": "text/plain" })
    res.end("Not found")
  })

  const wss = new WebSocketServer({ server, path: "/ws" })

  wss.on("connection", (ws) => {
    const sessionId = ulid()
    const toolContext: ToolContext = {
      workspaceRoot: params.config.workspaceRoot,
      enableShell: params.config.enableShell,
      enableWrite: params.config.enableWrite,
      maxFileReadChars: params.config.maxFileReadChars,
      maxToolOutputChars: params.config.maxToolOutputChars,
    }
    const tools = createBuiltInTools(toolContext)

    let messages: ChatMessage[] = []
    const ready = (async () => {
      messages = [{ role: "system", content: await buildSystemPrompt(params.config.workspaceRoot, params.role) }]
    })()

    const send = (msg: ServerToClient) => {
      ws.send(JSON.stringify(msg))
    }

    send({ type: "welcome", sessionId })

    ws.on("message", async (raw) => {
      await ready
      let parsed: ClientToServer
      try {
        parsed = JSON.parse(raw.toString("utf8")) as ClientToServer
      } catch (e) {
        send({ type: "error", message: `Invalid JSON: ${String(e)}` })
        return
      }

      if (parsed.type === "ping") {
        send({ type: "pong" })
        return
      }

      if (parsed.type !== "user_message") {
        send({ type: "error", message: `Unknown message type: ${(parsed as any).type}` })
        return
      }

      const userText = String(parsed.content ?? "").trim()
      if (!userText) return

      try {
        const result = await runAgentTask({
          provider: params.provider,
          model: params.config.model,
          messages,
          userInput: userText,
          tools,
          toolContext,
          maxSteps: params.config.maxSteps,
          onEvent: (event) => {
            if (event.type === "tool_call") send({ type: "tool_call", toolName: event.toolName, args: event.args })
            if (event.type === "tool_result")
              send({ type: "tool_result", toolName: event.toolName, result: event.result })
            if (event.type === "assistant_message") send({ type: "assistant_message", content: event.content })
            if (event.type === "error") send({ type: "error", message: event.message })
          },
        })
        messages = result.messages
      } catch (e) {
        send({ type: "error", message: String(e) })
      }
    })
  })

  await new Promise<void>((resolve) => server.listen(params.config.port, resolve))
  return server
}
