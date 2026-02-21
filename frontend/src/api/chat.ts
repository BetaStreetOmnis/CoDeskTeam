import axios from "axios"

export type ChatEvent = { type: string; [k: string]: unknown }

export type ChatAttachment = {
  kind?: "image" | "file"
  file_id: string
  filename?: string
  content_type?: string
}

export type ChatSecurityPreset = "safe" | "standard" | "power" | "custom"

export type ChatRequest = {
  message: string
  session_id?: string
  role?: string
  provider?: string
  model?: string
  project_id?: number
  security_preset?: ChatSecurityPreset
  enable_shell?: boolean
  enable_write?: boolean
  enable_browser?: boolean
  enable_dangerous?: boolean
  show_reasoning?: boolean
  attachments?: ChatAttachment[]
}

export type ChatResponse = {
  session_id: string
  assistant: string
  events: ChatEvent[]
}

export async function chat(req: ChatRequest, opts?: { signal?: AbortSignal }): Promise<ChatResponse> {
  const res = await axios.post("/api/chat", req, { signal: opts?.signal })
  return res.data as ChatResponse
}
