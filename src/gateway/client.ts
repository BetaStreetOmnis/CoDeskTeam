import { WebSocket } from "ws"
import { createInterface } from "node:readline/promises"
import process from "node:process"

type ServerToClient =
  | { type: "welcome"; sessionId: string }
  | { type: "pong" }
  | { type: "tool_call"; toolName: string; args: unknown }
  | { type: "tool_result"; toolName: string; result: unknown }
  | { type: "assistant_message"; content: string }
  | { type: "error"; message: string }

export async function connectAndChat(url: string): Promise<void> {
  const ws = new WebSocket(url)

  ws.on("message", (raw) => {
    let msg: ServerToClient
    try {
      msg = JSON.parse(raw.toString("utf8")) as ServerToClient
    } catch {
      process.stdout.write(String(raw) + "\n")
      return
    }

    if (msg.type === "welcome") process.stdout.write(`(connected) session=${msg.sessionId}\n`)
    if (msg.type === "tool_call") process.stdout.write(`(tool_call) ${msg.toolName} ${JSON.stringify(msg.args)}\n`)
    if (msg.type === "tool_result") process.stdout.write(`(tool_result) ${msg.toolName}\n`)
    if (msg.type === "assistant_message") process.stdout.write(`${msg.content}\n`)
    if (msg.type === "error") process.stdout.write(`(error) ${msg.message}\n`)
  })

  await new Promise<void>((resolve, reject) => {
    ws.on("open", () => resolve())
    ws.on("error", (e) => reject(e))
  })

  const rl = createInterface({ input: process.stdin, output: process.stdout })
  try {
    for (;;) {
      const line = await rl.question("> ")
      const trimmed = line.trim()
      if (!trimmed) continue
      if (trimmed === ":exit" || trimmed === ":quit") break
      ws.send(JSON.stringify({ type: "user_message", content: trimmed }))
    }
  } finally {
    rl.close()
    ws.close()
  }
}
