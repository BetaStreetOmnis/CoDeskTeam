import axios from "axios"

export type HistorySessionItem = {
  session_id: string
  title: string
  role: string
  provider: string
  model: string
  project_id: number | null
  created_at: string
  updated_at: string
  last_message?: string | null
}

export type HistoryAttachment = {
  kind: "image" | "file"
  file_id: string
  filename?: string | null
  content_type?: string | null
  download_url: string
}

export type HistoryMessageItem = {
  id: number
  role: "user" | "assistant"
  content: string
  created_at: string
  attachments: HistoryAttachment[]
  events?: any | null
}

export type HistorySessionDetailResponse = {
  session: HistorySessionItem
  messages: HistoryMessageItem[]
}

export type HistoryFileItem = {
  file_id: string
  kind: string
  filename: string
  content_type: string
  size_bytes: number
  project_id: number | null
  session_id: string | null
  created_at: string
  download_url: string
}

export type HistorySearchHit = {
  source: "workspace" | "history"
  rel_path: string
  absolute_path: string
  line_no: number
  column_no: number
  preview: string
}

export async function listHistorySessions(params?: {
  project_id?: number
  limit?: number
  offset?: number
}): Promise<HistorySessionItem[]> {
  const res = await axios.get("/api/history/sessions", { params })
  return res.data as HistorySessionItem[]
}

export async function getHistorySession(session_id: string): Promise<HistorySessionDetailResponse> {
  const res = await axios.get(`/api/history/sessions/${encodeURIComponent(session_id)}`)
  return res.data as HistorySessionDetailResponse
}

export async function deleteHistorySession(session_id: string): Promise<void> {
  await axios.delete(`/api/history/sessions/${encodeURIComponent(session_id)}`)
}

export async function listHistoryFiles(params?: {
  project_id?: number
  session_id?: string
  kind?: string
  limit?: number
  offset?: number
}): Promise<HistoryFileItem[]> {
  const res = await axios.get("/api/history/files", { params })
  return res.data as HistoryFileItem[]
}

export async function searchHistory(params: {
  q: string
  project_id?: number
  sub_path?: string
  include_workspace?: boolean
  include_history?: boolean
  limit?: number
}): Promise<HistorySearchHit[]> {
  const res = await axios.get("/api/history/search", { params })
  return res.data as HistorySearchHit[]
}
