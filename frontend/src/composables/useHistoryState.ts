import { computed, ref, watch, type Ref } from "vue"

import { listHistoryFiles, listHistorySessions, searchHistory } from "../api"
import type { HistoryFileItem, HistorySearchHit, HistorySessionDetailResponse, HistorySessionItem, MeResponse } from "../api"

type ErrorFormatter = (error: any) => string

type Options = {
  me: Ref<MeResponse | null>
  activeProjectId: Ref<number>
  projectNameFromId: (projectId: number | null | undefined) => string
  formatError: ErrorFormatter
  handleUnauthorized: (error: any) => boolean
}

type ParsedSearchCommand = {
  q: string
  project_id?: number
  sub_path?: string
  include_workspace: boolean
  include_history: boolean
  limit: number
}

function _tokenizeCommand(text: string): string[] {
  const out: string[] = []
  const re = /"([^"]*)"|'([^']*)'|(\S+)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    const token = m[1] ?? m[2] ?? m[3] ?? ""
    const v = token.trim()
    if (v) out.push(v)
  }
  return out
}

export function useHistoryState({ me, activeProjectId, projectNameFromId, formatError, handleUnauthorized }: Options) {
  const historyTab = ref<"sessions" | "files" | "search">("sessions")
  const historyScope = ref<"current" | "all">(localStorage.getItem("aistaff_history_scope") === "all" ? "all" : "current")

  const historySearch = ref("")
  const historyFileKindFilter = ref<string>("")
  const historySessions = ref<HistorySessionItem[]>([])
  const historyFiles = ref<HistoryFileItem[]>([])
  const historySessionsBusy = ref(false)
  const historyFilesBusy = ref(false)
  const historyError = ref<string | null>(null)
  const selectedHistorySessionId = ref<string | null>(null)

  const historyDirectoryCommand = ref(localStorage.getItem("aistaff_history_cmd") || "")
  const historySearchHits = ref<HistorySearchHit[]>([])
  const historySearchBusy = ref(false)
  const historySearchExecuted = ref(false)

  const showHistoryModal = ref(false)
  const historyDetail = ref<HistorySessionDetailResponse | null>(null)
  const historyDetailBusy = ref(false)
  const historyDetailError = ref<string | null>(null)

  const filteredHistorySessions = computed(() => {
    const q = historySearch.value.trim().toLowerCase()
    if (!q) return historySessions.value
    return historySessions.value.filter((s) => {
      const hay = [
        s.session_id,
        s.title || "",
        s.last_message || "",
        s.role || "",
        s.provider || "",
        s.model || "",
        projectNameFromId(s.project_id),
      ]
        .join(" ")
        .toLowerCase()
      return hay.includes(q)
    })
  })

  const filteredHistoryFiles = computed(() => {
    const q = historySearch.value.trim().toLowerCase()
    const kind = String(historyFileKindFilter.value || "").trim().toLowerCase()
    return historyFiles.value.filter((f) => {
      if (kind && String(f.kind || "").toLowerCase() !== kind) return false
      if (!q) return true
      const hay = [
        f.file_id,
        f.filename || "",
        f.kind || "",
        f.content_type || "",
        f.session_id || "",
        projectNameFromId(f.project_id),
      ]
        .join(" ")
        .toLowerCase()
      return hay.includes(q)
    })
  })

  function historyQueryProjectId(): number | undefined {
    if (historyScope.value === "all") return undefined
    return activeProjectId.value > 0 ? activeProjectId.value : 0
  }

  function parseHistoryDirectoryCommand(rawCommand: string): ParsedSearchCommand {
    const raw = String(rawCommand || "").trim()
    if (!raw) {
      throw new Error("请输入检索命令，例如：grep 报检单 --path=docs")
    }

    let normalized = raw
    if (normalized.startsWith("/") || normalized.startsWith("!")) normalized = normalized.slice(1).trim()
    const tokens = _tokenizeCommand(normalized)
    if (!tokens.length) throw new Error("命令为空，请输入检索关键词。")

    const head = (tokens[0] || "").toLowerCase()
    const supportedHeads = new Set(["grep", "search", "find", "rg"])
    const contentTokens = supportedHeads.has(head) ? tokens.slice(1) : tokens

    let includeWorkspace = true
    let includeHistory = true
    let projectId = historyScope.value === "all" ? undefined : activeProjectId.value > 0 ? activeProjectId.value : 0
    let subPath: string | undefined = undefined
    let limit = 80

    const keywordParts: string[] = []
    for (const token of contentTokens) {
      const lower = token.toLowerCase()

      if (lower === "--workspace") {
        includeWorkspace = true
        includeHistory = false
        continue
      }
      if (lower === "--history") {
        includeWorkspace = false
        includeHistory = true
        continue
      }
      if (lower === "--both") {
        includeWorkspace = true
        includeHistory = true
        continue
      }
      if (lower === "--all" || lower === "--all-projects") {
        projectId = undefined
        continue
      }
      if (lower === "--current") {
        projectId = activeProjectId.value > 0 ? activeProjectId.value : 0
        continue
      }
      if (lower.startsWith("--project=")) {
        const rawValue = token.slice("--project=".length).trim()
        const n = Number(rawValue)
        if (!Number.isFinite(n)) throw new Error("--project 参数无效，请填写数字项目ID。")
        projectId = n > 0 ? Math.floor(n) : 0
        continue
      }
      if (lower.startsWith("--path=")) {
        const rawValue = token.slice("--path=".length).trim()
        subPath = rawValue || undefined
        continue
      }
      if (lower.startsWith("in:")) {
        const rawValue = token.slice(3).trim()
        subPath = rawValue || undefined
        continue
      }
      if (lower.startsWith("--limit=")) {
        const rawValue = token.slice("--limit=".length).trim()
        const n = Number(rawValue)
        if (!Number.isFinite(n)) throw new Error("--limit 参数无效，请填写数字。")
        limit = Math.max(1, Math.min(400, Math.floor(n)))
        continue
      }

      keywordParts.push(token)
    }

    const q = keywordParts.join(" ").trim()
    if (!q) {
      throw new Error("缺少检索关键词，例如：grep 报检单 --path=docs")
    }

    if (!includeWorkspace && !includeHistory) {
      includeWorkspace = true
      includeHistory = true
    }

    return {
      q,
      project_id: projectId,
      sub_path: subPath,
      include_workspace: includeWorkspace,
      include_history: includeHistory,
      limit,
    }
  }

  async function refreshHistorySessions() {
    if (!me.value) return
    historySessionsBusy.value = true
    historyError.value = null
    try {
      const pid = historyQueryProjectId()
      historySessions.value = await listHistorySessions(
        pid === undefined ? { limit: 50, offset: 0 } : { project_id: pid, limit: 50, offset: 0 },
      )
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      historyError.value = formatError(error)
    } finally {
      historySessionsBusy.value = false
    }
  }

  async function refreshHistoryFiles() {
    if (!me.value) return
    historyFilesBusy.value = true
    historyError.value = null
    try {
      const pid = historyQueryProjectId()
      historyFiles.value = await listHistoryFiles(
        pid === undefined ? { limit: 50, offset: 0 } : { project_id: pid, limit: 50, offset: 0 },
      )
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      historyError.value = formatError(error)
    } finally {
      historyFilesBusy.value = false
    }
  }

  async function runHistoryDirectorySearch(rawCommand?: string) {
    if (!me.value) return

    const command = String(rawCommand ?? historyDirectoryCommand.value ?? "").trim()
    historyDirectoryCommand.value = command
    localStorage.setItem("aistaff_history_cmd", command)
    historySearchExecuted.value = true

    let parsed: ParsedSearchCommand
    try {
      parsed = parseHistoryDirectoryCommand(command)
    } catch (error: any) {
      historySearchHits.value = []
      historyError.value = error?.message || "检索命令不合法"
      return
    }

    historySearchBusy.value = true
    historyError.value = null
    try {
      historySearchHits.value = await searchHistory(parsed)
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      historyError.value = formatError(error)
    } finally {
      historySearchBusy.value = false
    }
  }

  async function refreshHistory() {
    await Promise.all([refreshHistorySessions(), refreshHistoryFiles()])
  }

  function closeHistoryModal() {
    showHistoryModal.value = false
    selectedHistorySessionId.value = null
    historyDetail.value = null
    historyDetailError.value = null
    historyDetailBusy.value = false
  }

  watch(historyScope, (value) => {
    localStorage.setItem("aistaff_history_scope", value)
    void refreshHistory()
    if (historyTab.value === "search" && historySearchExecuted.value) {
      void runHistoryDirectorySearch()
    }
  })

  return {
    historyTab,
    historyScope,
    historySearch,
    historyFileKindFilter,
    historySessions,
    historyFiles,
    historySessionsBusy,
    historyFilesBusy,
    historyError,
    selectedHistorySessionId,
    historyDirectoryCommand,
    historySearchHits,
    historySearchBusy,
    historySearchExecuted,
    showHistoryModal,
    historyDetail,
    historyDetailBusy,
    historyDetailError,
    filteredHistorySessions,
    filteredHistoryFiles,
    refreshHistorySessions,
    refreshHistoryFiles,
    runHistoryDirectorySearch,
    refreshHistory,
    closeHistoryModal,
  }
}
