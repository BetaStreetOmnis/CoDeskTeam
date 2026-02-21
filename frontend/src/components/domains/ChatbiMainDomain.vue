<template>
  <main class="main">
    <div class="chatHead">
      <div>
        <h2 class="chatTitle"><span class="msIcon h2Icon" aria-hidden="true">query_stats</span>智能问数</h2>
        <div class="chatMeta">
          <span class="metaPill">工作区：{{ activeWorkspaceLabel }}</span>
          <span class="metaPill">数据源：{{ selectedDatasourceIds.length || "自动" }}</span>
          <span class="metaPill">流式反馈</span>
        </div>
      </div>
      <div class="chatActions">
        <button class="ghostBtn iconBtn" :class="{ active: showLeft }" type="button" @click="showLeft = !showLeft">
          <span class="msIcon btnIcon" aria-hidden="true">left_panel_open</span>
          <span>左栏</span>
        </button>
        <button class="ghostBtn iconBtn" :class="{ active: showRight }" type="button" @click="showRight = !showRight">
          <span class="msIcon btnIcon" aria-hidden="true">right_panel_open</span>
          <span>结果</span>
        </button>
        <button class="ghostBtn iconBtn" :disabled="busy" type="button" @click="newQuery">
          <span class="msIcon btnIcon" aria-hidden="true">add_comment</span>
          <span>新问题</span>
        </button>
      </div>
    </div>

    <div class="chatBody">
      <div class="card" style="margin-bottom: 12px;">
        <div class="cardHead">
          <div>
            <h3><span class="msIcon h3Icon" aria-hidden="true">database</span>数据源</h3>
            <div class="subtle">不选则自动使用“已启用”的数据源</div>
          </div>
          <div class="cardHeadActions">
            <button class="ghostBtn" :disabled="dsBusy" type="button" @click="loadDatasources">
              <span class="msIcon btnIcon" aria-hidden="true">refresh</span>
              <span>{{ dsBusy ? "加载中…" : "刷新" }}</span>
            </button>
          </div>
        </div>

        <div v-if="datasources.length" class="chipsWrap">
          <label v-for="s in datasources" :key="s.id" class="chip">
            <input v-model="selectedDatasourceIds" type="checkbox" :value="s.id" />
            <span class="chipText">{{ s.name }}</span>
          </label>
        </div>
        <div v-else class="subtle" style="padding: 0 12px 12px;">暂无可用数据源。</div>
      </div>

      <div v-if="timeline.length === 0" class="empty" style="margin-top: 14px;">
        <div class="emptyTitle">从一个问题开始</div>
        <div class="emptyHint">例如：近30天未处理火警数量趋势</div>
        <div class="emptyChips">
          <button class="suggestChip" type="button" @click="applyExample('近30天未处理火警数量趋势')">趋势</button>
          <button class="suggestChip" type="button" @click="applyExample('按单位统计本月火警数量 TOP10')">TOP10</button>
          <button class="suggestChip" type="button" @click="applyExample('按站点统计装备在库数量对比')">对比</button>
        </div>
      </div>

      <div v-for="item in timeline" :key="item.id" class="bubble assistant" style="margin-bottom: 10px;">
        <div class="bubbleMeta">
          <span class="who">AI</span>
          <span class="when">{{ formatTime(item.ts) }}</span>
        </div>

        <div class="md">
          <div class="subtle">问题：{{ item.question }}</div>
        </div>

        <details class="thoughtBlock" :open="!!item.sql_explain">
          <summary>SQL 解释</summary>
          <div class="md chatbiMarkdown" v-html="renderMarkdown(item.sql_explain || '（空）')" />
        </details>

        <details class="thoughtBlock" :open="!!item.sql">
          <summary>SQL</summary>
          <div
            class="md chatbiMarkdown"
            v-html="renderMarkdown(item.sql ? ('```sql\\n' + item.sql + '\\n```') : '（空）')"
          />
        </details>

        <details class="thoughtBlock" :open="!!item.analysis">
          <summary>分析</summary>
          <div class="md chatbiMarkdown" v-html="renderMarkdown(item.analysis || '（空）')" />
        </details>

        <div class="row" style="gap: 10px; flex-wrap: wrap;">
          <button class="ghostBtn" type="button" @click="setPreview(item)">在右侧查看结果</button>
          <button class="ghostBtn" :disabled="!item.sql" type="button" @click="copyToClipboard(item.sql || '')">复制 SQL</button>
          <button class="ghostBtn" :disabled="!item.result?.data?.length" type="button" @click="downloadCsv(item)">
            导出 CSV
          </button>
        </div>
      </div>

      <div v-if="error" class="error">{{ error }}</div>
    </div>

    <div class="composer">
      <textarea
        v-model="question"
        class="composerInput"
        :disabled="busy"
        placeholder="输入要查询的问题…"
        rows="2"
        @keydown.enter.exact.prevent="send"
        @keydown.enter.shift.exact.stop
      />
      <div class="composerActions">
        <div class="subtle">Enter 发送 · Shift+Enter 换行</div>
        <div class="composerButtons">
          <button class="ghostBtn" :disabled="!busy" type="button" @click="cancel">
            <span class="msIcon btnIcon" aria-hidden="true">stop</span>
            <span>停止</span>
          </button>
          <button class="primaryBtn" :disabled="busy || !question.trim()" type="button" @click="send">
            <span class="msIcon btnIcon" aria-hidden="true">send</span>
            <span>{{ busy ? "查询中…" : "发送" }}</span>
          </button>
        </div>
      </div>
    </div>
  </main>

  <aside v-if="showRight" class="previewSide">
    <section class="card previewCard">
      <div class="cardHead">
        <h3><span class="msIcon h3Icon" aria-hidden="true">dock_to_right</span>结果预览</h3>
        <button v-if="previewItem" class="ghostBtn iconBtn" type="button" @click="previewItem = null">
          <span class="msIcon btnIcon" aria-hidden="true">ink_eraser</span>
          <span>清空</span>
        </button>
      </div>

      <div class="previewBody">
        <div v-if="!previewItem" class="subtle">暂无结果：先在左侧提一个问题。</div>

        <template v-else>
          <div class="subtle" style="margin-bottom: 10px;">问题：{{ previewItem.question }}</div>
          <div v-if="previewItem.result?.chart" class="subtle" style="margin-bottom: 10px;">
            图表建议：{{ chartLabel(previewItem.result.chart) }}
          </div>
          <div v-if="previewItem.result?.truncated" class="subtle" style="margin-bottom: 10px;">
            结果已截断：仅展示前 {{ previewItem.result.max_rows }} 条
          </div>

          <div class="tableWrap">
            <table class="table">
              <thead>
                <tr>
                  <th v-for="c in previewColumns" :key="c" class="th">{{ c }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(r, idx) in previewRows" :key="idx">
                  <td v-for="c in previewColumns" :key="c" class="td">{{ formatCell(r[c]) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </section>
  </aside>
</template>

<script lang="ts">
import { defineComponent, onMounted, ref, watch, computed, type PropType } from "vue"
import { chatbiChatStream, listChatbiDatasources, type ChatbiDatasource, type ChatbiStreamEvent } from "../../api"

type ChatbiTimelineItem = {
  id: string
  ts: number
  question: string
  sql: string
  sql_explain: string
  analysis: string
  result: any | null
}

export default defineComponent({
  name: "ChatbiMainDomain",
  props: {
    ctx: {
      type: Object as PropType<Record<string, any>>,
      required: true,
    },
  },
  setup(props) {
    const ctx = props.ctx as Record<string, any>

    const datasources = ref<ChatbiDatasource[]>([])
    const selectedDatasourceIds = ref<string[]>([])
    const dsBusy = ref(false)

    const question = ref("")
    const error = ref<string | null>(null)
    const busy = ref(false)
    const abortCtl = ref<AbortController | null>(null)

    const timeline = ref<ChatbiTimelineItem[]>([])
    const previewItem = ref<ChatbiTimelineItem | null>(null)

    const previewColumns = computed(() => {
      const row = previewItem.value?.result?.data?.[0]
      if (!row || typeof row !== "object") return []
      return Object.keys(row)
    })
    const previewRows = computed(() => {
      const data = previewItem.value?.result?.data
      if (!Array.isArray(data)) return []
      return (data as Array<Record<string, any>>).slice(0, 200)
    })

    function _formatErr(e: any): string {
      const detail = e?.response?.data?.detail
      if (typeof detail === "string" && detail.trim()) return detail
      if (typeof e?.message === "string" && e.message.trim()) return e.message
      try {
        return JSON.stringify(e)
      } catch {
        return String(e)
      }
    }

    function _handleUnauthorized(err: any): boolean {
      const status = err?.response?.status ?? err?.status
      if (status === 401) {
        try {
          localStorage.removeItem("aistaff_token")
        } catch {
          // ignore
        }
        window.location.reload()
        return true
      }
      return false
    }

    async function loadDatasources() {
      dsBusy.value = true
      error.value = null
      try {
        const res = await listChatbiDatasources()
        datasources.value = res.data ?? []

        const stored = (() => {
          try {
            return localStorage.getItem("aistaff_chatbi_sources") ?? ""
          } catch {
            return ""
          }
        })()
        const storedIds = stored ? stored.split(",").map((s) => s.trim()).filter(Boolean) : []
        const enabledIds = (datasources.value ?? []).filter((s) => s.enabled !== false).map((s) => s.id)
        selectedDatasourceIds.value = storedIds.length ? storedIds.filter((id) => enabledIds.includes(id)) : enabledIds
        if (selectedDatasourceIds.value.length === 0) selectedDatasourceIds.value = enabledIds
      } catch (e: any) {
        if (_handleUnauthorized(e)) return
        error.value = _formatErr(e)
      } finally {
        dsBusy.value = false
      }
    }

    watch(selectedDatasourceIds, (v) => {
      try {
        localStorage.setItem("aistaff_chatbi_sources", (v ?? []).join(","))
      } catch {
        // ignore
      }
    })

    function cancel() {
      abortCtl.value?.abort()
      abortCtl.value = null
      busy.value = false
    }

    function newQuery() {
      error.value = null
      question.value = ""
    }

    function applyExample(text: string) {
      question.value = text
    }

    function setPreview(item: ChatbiTimelineItem) {
      previewItem.value = item
      ctx.showRight.value = true
    }

    function formatCell(v: any): string {
      if (v === null || v === undefined) return ""
      if (typeof v === "object") {
        try {
          return JSON.stringify(v)
        } catch {
          return String(v)
        }
      }
      return String(v)
    }

    function chartLabel(chart: any): string {
      const t = String(chart?.type ?? "table")
      const title = String(chart?.title ?? "")
      return title ? `${t} · ${title}` : t
    }

    function downloadCsv(item: ChatbiTimelineItem) {
      const data = item.result?.data
      if (!Array.isArray(data) || data.length === 0) return
      const cols = Object.keys(data[0] ?? {})
      const escape = (s: any) => {
        const raw = String(s ?? "")
        if (/[",\n]/.test(raw)) return `"${raw.replace(/\"/g, '""')}"`
        return raw
      }
      const lines: string[] = []
      lines.push(cols.map(escape).join(","))
      for (const r of data.slice(0, 5000)) {
        lines.push(cols.map((c) => escape((r as any)[c])).join(","))
      }
      const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "chatbi_result.csv"
      a.click()
      URL.revokeObjectURL(url)
    }

    async function send() {
      if (!question.value.trim()) return
      if (busy.value) cancel()

      error.value = null
      busy.value = true

      const id = `${Date.now()}_${Math.random().toString(16).slice(2)}`
      const item: ChatbiTimelineItem = {
        id,
        ts: Date.now(),
        question: question.value.trim(),
        sql: "",
        sql_explain: "",
        analysis: "",
        result: null,
      }
      timeline.value = [item, ...timeline.value].slice(0, 30)
      previewItem.value = item
      ctx.showRight.value = true

      const ctl = new AbortController()
      abortCtl.value = ctl

      try {
        const onEvent = (ev: ChatbiStreamEvent) => {
          const idx = timeline.value.findIndex((x) => x.id === id)
          if (idx < 0) return
          const cur = timeline.value[idx]
          if (!cur) return
          if (ev.event === "chat") {
            cur.analysis = String(ev.data?.reply ?? "")
          } else if (ev.event === "sql_explain_delta") {
            cur.sql_explain += String(ev.data?.delta ?? "")
          } else if (ev.event === "sql_explain") {
            cur.sql_explain = String(ev.data?.sql_explain ?? cur.sql_explain)
          } else if (ev.event === "sql_delta") {
            cur.sql += String(ev.data?.delta ?? "")
          } else if (ev.event === "sql") {
            cur.sql = String(ev.data?.sql ?? cur.sql)
          } else if (ev.event === "analysis_delta") {
            cur.analysis += String(ev.data?.delta ?? "")
          } else if (ev.event === "analysis") {
            cur.analysis = String(ev.data?.analysis ?? cur.analysis)
          } else if (ev.event === "result") {
            cur.result = ev.data?.result ?? null
          } else if (ev.event === "error") {
            error.value = String(ev.data?.error ?? "查询失败")
          }
          // Re-assign to trigger Vue update when mutating nested object.
          timeline.value = [...timeline.value]
          if (previewItem.value?.id === id) previewItem.value = { ...cur }
        }

        await chatbiChatStream(
          {
            question: item.question,
            datasource_ids: selectedDatasourceIds.value,
            history: [],
          },
          { onEvent },
          { signal: ctl.signal },
        )
      } catch (e: any) {
        if (e?.name === "AbortError") return
        if (_handleUnauthorized(e)) return
        error.value = _formatErr(e)
      } finally {
        busy.value = false
        abortCtl.value = null
      }
    }

    onMounted(() => {
      loadDatasources()
    })

    // Extend the shared ctx object, so template type-checking remains permissive
    // and keeps consistency with other Domain components in this repo.
    ctx.datasources = datasources
    ctx.selectedDatasourceIds = selectedDatasourceIds
    ctx.dsBusy = dsBusy
    ctx.question = question
    ctx.error = error
    ctx.busy = busy
    ctx.timeline = timeline
    ctx.previewItem = previewItem
    ctx.previewColumns = previewColumns
    ctx.previewRows = previewRows
    ctx.loadDatasources = loadDatasources
    ctx.cancel = cancel
    ctx.newQuery = newQuery
    ctx.applyExample = applyExample
    ctx.setPreview = setPreview
    ctx.formatCell = formatCell
    ctx.chartLabel = chartLabel
    ctx.downloadCsv = downloadCsv
    ctx.send = send

    return ctx
  },
})
</script>

<style scoped>
.chipsWrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 12px 12px;
}
.chipText {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chatbiMarkdown :deep(p:first-child) {
  margin-top: 0;
}
.tableWrap {
  overflow: auto;
  margin-top: 8px;
  border-radius: 10px;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.08));
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.th,
.td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  vertical-align: top;
  white-space: nowrap;
}
</style>
