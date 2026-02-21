import axios from "axios"

export type ChatbiDatasource = {
  id: string
  name: string
  description?: string
  db_type?: string
  tables?: string[]
  enabled?: boolean
  is_default?: boolean
}

export type ChatbiListDatasourcesResponse = { success: boolean; data: ChatbiDatasource[] }

export async function listChatbiDatasources(): Promise<ChatbiListDatasourcesResponse> {
  const res = await axios.get("/api/chatbi/datasources")
  return res.data as ChatbiListDatasourcesResponse
}

export type ChatbiUpsertDatasourceRequest = {
  id: string
  name?: string
  description?: string
  db_type?: string
  db_path?: string
  db_url?: string
  tables?: string[]
  enabled?: boolean
}

export type ChatbiUpsertDatasourceResponse = { success: boolean; data: ChatbiDatasource }

export async function upsertChatbiDatasource(req: ChatbiUpsertDatasourceRequest): Promise<ChatbiUpsertDatasourceResponse> {
  const res = await axios.post("/api/chatbi/datasources", req)
  return res.data as ChatbiUpsertDatasourceResponse
}

export async function deleteChatbiDatasource(id: string): Promise<{ success: boolean }> {
  const res = await axios.delete(`/api/chatbi/datasources/${encodeURIComponent(id)}`)
  return res.data as { success: boolean }
}

export type ChatbiChatRequest = {
  question?: string
  query?: string
  datasource_ids?: string[]
  history?: Array<{ role: string; content: string }>
}

export type ChatbiChatResponse =
  | { success: true; mode: "chat"; reply: string; question: string }
  | {
      success: true
      question?: string
      sql: string
      sql_explain?: string
      data: Array<Record<string, unknown>>
      count: number
      truncated: boolean
      max_rows: number
      analysis: string
      chart?: Record<string, unknown> | null
    }
  | { success: false; error: string }

export async function chatbiChat(req: ChatbiChatRequest, opts?: { signal?: AbortSignal }): Promise<ChatbiChatResponse> {
  const res = await axios.post("/api/chatbi/chat", req, { signal: opts?.signal })
  return res.data as ChatbiChatResponse
}

export type ChatbiSqlRunRequest = { sql: string; datasource_ids?: string[]; question?: string }

export async function chatbiRunSql(req: ChatbiSqlRunRequest, opts?: { signal?: AbortSignal }): Promise<any> {
  const res = await axios.post("/api/chatbi/sql/run", req, { signal: opts?.signal })
  return res.data as any
}

export type ChatbiStreamEvent =
  | { event: "chat"; data: any }
  | { event: "sql_explain_delta"; data: { delta: string } }
  | { event: "sql_explain"; data: { sql_explain: string } }
  | { event: "sql_delta"; data: { delta: string } }
  | { event: "sql"; data: { sql: string } }
  | { event: "analysis_delta"; data: { delta: string } }
  | { event: "analysis"; data: { analysis: string } }
  | { event: "result"; data: { result: any } }
  | { event: "error"; data: { error: string } }
  | { event: "done"; data: { success: boolean } }
  | { event: string; data: any }

function _getAuthToken(): string | null {
  try {
    return localStorage.getItem("aistaff_token")
  } catch {
    return null
  }
}

export async function chatbiChatStream(
  req: ChatbiChatRequest,
  handlers: {
    onEvent?: (ev: ChatbiStreamEvent) => void
    onError?: (err: unknown) => void
  },
  opts?: { signal?: AbortSignal; token?: string | null },
): Promise<void> {
  const token = opts?.token ?? _getAuthToken()
  const res = await fetch("/api/chatbi/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(req ?? {}),
    signal: opts?.signal,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => "")
    const err: any = new Error(`HTTP ${res.status}: ${text || res.statusText}`)
    err.status = res.status
    throw err
  }
  if (!res.body) return

  const decoder = new TextDecoder("utf-8")
  const reader = res.body.getReader()

  let buf = ""
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      buf = buf.replace(/\r\n/g, "\n")

      while (true) {
        const sep = buf.indexOf("\n\n")
        if (sep < 0) break
        const raw = buf.slice(0, sep)
        buf = buf.slice(sep + 2)

        let event = "message"
        const dataLines: string[] = []
        for (const line of raw.split("\n")) {
          if (line.startsWith("event:")) event = line.slice("event:".length).trim()
          if (line.startsWith("data:")) dataLines.push(line.slice("data:".length).trimStart())
        }
        const dataStr = dataLines.join("\n").trim()
        let data: any = {}
        if (dataStr) {
          try {
            data = JSON.parse(dataStr)
          } catch {
            data = { raw: dataStr }
          }
        }

        const ev: ChatbiStreamEvent = { event, data }
        handlers.onEvent?.(ev)
        if (event === "done") return
      }
    }
  } catch (err) {
    handlers.onError?.(err)
    throw err
  } finally {
    try {
      reader.releaseLock()
    } catch {
      // ignore
    }
  }
}
