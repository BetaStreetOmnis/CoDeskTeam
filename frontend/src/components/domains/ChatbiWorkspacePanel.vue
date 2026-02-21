<template>
  <div class="chatbi">
    <div class="row" style="justify-content: space-between; align-items: center;">
      <div class="subtle">数据源</div>
      <button class="ghostBtn" :disabled="busy || dsBusy" type="button" @click="loadDatasources">
        <span class="msIcon btnIcon" aria-hidden="true">refresh</span>
        <span>{{ dsBusy ? "加载中…" : "刷新" }}</span>
      </button>
    </div>

    <div v-if="datasources.length" class="dsList">
      <label v-for="s in datasources" :key="s.id" class="chip">
        <input v-model="selectedDatasourceIds" type="checkbox" :value="s.id" />
        <span class="dsName">{{ s.name }}</span>
      </label>
    </div>
    <div v-else class="subtle">暂无数据源（或未登录）。</div>

    <div class="row">
      <textarea
        v-model="question"
        class="textarea"
        :disabled="busy"
        rows="3"
        placeholder="输入问题，例如：近30天未处理火警数量趋势"
      />
    </div>
    <div class="row">
      <button class="primaryBtn" :disabled="busy || !question.trim()" type="button" @click="ask">
        {{ busy ? "查询中…" : "问数" }}
      </button>
      <button class="ghostBtn" :disabled="!busy" type="button" @click="cancel">停止</button>
      <button class="ghostBtn" :disabled="busy" type="button" @click="clearAll">清空</button>
    </div>

    <div v-if="error" class="error">{{ error }}</div>

    <details class="resultBlock" :open="!!sqlExplain">
      <summary>SQL 解释</summary>
      <pre class="pre">{{ sqlExplain || "（空）" }}</pre>
    </details>

    <details class="resultBlock" :open="!!sql">
      <summary>SQL</summary>
      <textarea v-model="sql" class="textarea mono" :disabled="busy" rows="5" placeholder="生成的 SQL 会显示在这里…" />
      <div class="row">
        <button class="ghostBtn" :disabled="busy || !sql.trim()" type="button" @click="runSql">执行 SQL</button>
      </div>
    </details>

    <details class="resultBlock" :open="!!analysis">
      <summary>分析</summary>
      <pre class="pre">{{ analysis || "（空）" }}</pre>
    </details>

    <details v-if="result" class="resultBlock" open>
      <summary>结果（{{ result.count ?? 0 }} 条{{ result.truncated ? "，已截断" : "" }}）</summary>
      <div class="row" style="justify-content: space-between; align-items: center;">
        <div v-if="result.chart" class="subtle">图表建议：{{ chartLabel(result.chart) }}</div>
        <button class="ghostBtn" type="button" @click="downloadCsv">导出 CSV</button>
      </div>
      <div class="tableWrap">
        <table class="table">
          <thead>
            <tr>
              <th v-for="c in columns" :key="c" class="th">{{ c }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, idx) in rows" :key="idx">
              <td v-for="c in columns" :key="c" class="td">{{ formatCell(r[c]) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>

    <details class="resultBlock">
      <summary>数据源管理（管理员）</summary>
      <div class="subtle">
        仅团队管理员可新增/删除。远程库连接字符串示例：
        <span class="mono">postgresql+psycopg://user:pass@host:5432/db</span>
      </div>
      <div class="row">
        <input v-model="dsForm.id" class="input mono" :disabled="dsSaveBusy" placeholder="id（如 sales）" />
      </div>
      <div class="row">
        <input v-model="dsForm.name" class="input" :disabled="dsSaveBusy" placeholder="名称" />
      </div>
      <div class="row">
        <input v-model="dsForm.description" class="input" :disabled="dsSaveBusy" placeholder="描述（可选）" />
      </div>
      <div class="row">
        <select v-model="dsForm.db_type" class="input" :disabled="dsSaveBusy">
          <option value="sqlite">sqlite</option>
          <option value="postgres">postgres</option>
          <option value="mysql">mysql</option>
        </select>
      </div>
      <div class="row" v-if="dsForm.db_type === 'sqlite'">
        <input v-model="dsForm.db_path" class="input mono" :disabled="dsSaveBusy" placeholder="SQLite 文件路径（服务器上）" />
      </div>
      <div class="row" v-else>
        <input v-model="dsForm.db_url" class="input mono" :disabled="dsSaveBusy" placeholder="DB URL（服务器上可直连）" />
      </div>
      <div class="row">
        <textarea
          v-model="dsForm.tablesText"
          class="textarea mono"
          :disabled="dsSaveBusy"
          rows="2"
          placeholder="表名列表（逗号/换行分隔），例如：orders, order_items"
        />
      </div>
      <div class="row">
        <label class="chip">
          <input v-model="dsForm.enabled" type="checkbox" :disabled="dsSaveBusy" />
          <span>启用</span>
        </label>
      </div>
      <div class="row">
        <button class="primaryBtn" :disabled="dsSaveBusy || !dsForm.id.trim()" type="button" @click="saveDatasource">
          {{ dsSaveBusy ? "保存中…" : "保存数据源" }}
        </button>
      </div>
      <div v-if="dsManageError" class="error">{{ dsManageError }}</div>
      <div class="subtle" style="margin-top: 10px;">现有数据源：</div>
      <div class="tableWrap">
        <table class="table tableTiny">
          <thead>
            <tr>
              <th class="th">ID</th>
              <th class="th">名称</th>
              <th class="th">类型</th>
              <th class="th">表</th>
              <th class="th"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in datasources" :key="s.id">
              <td class="td mono">{{ s.id }}</td>
              <td class="td">{{ s.name }}</td>
              <td class="td mono">{{ s.db_type ?? "sqlite" }}</td>
              <td class="td mono">{{ (s.tables ?? []).join(", ") }}</td>
              <td class="td" style="text-align: right;">
                <button class="ghostBtn" :disabled="dsSaveBusy || busy || s.is_default" type="button" @click="removeDatasource(s.id)">
                  删除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { chatbiChatStream, chatbiRunSql, deleteChatbiDatasource, listChatbiDatasources, upsertChatbiDatasource, type ChatbiDatasource } from "../../api"

const datasources = ref<ChatbiDatasource[]>([])
const selectedDatasourceIds = ref<string[]>([])
const dsBusy = ref(false)

const question = ref("")
const sqlExplain = ref("")
const sql = ref("")
const analysis = ref("")
const result = ref<any | null>(null)

const error = ref<string | null>(null)
const busy = ref(false)
const abortCtl = ref<AbortController | null>(null)

const columns = computed(() => {
  const row = result.value?.data?.[0]
  if (!row || typeof row !== "object") return []
  return Object.keys(row)
})
const rows = computed(() => {
  const data = result.value?.data
  if (!Array.isArray(data)) return []
  return data.slice(0, 200) as Array<Record<string, any>>
})

const dsManageError = ref<string | null>(null)
const dsSaveBusy = ref(false)
const dsForm = reactive({
  id: "",
  name: "",
  description: "",
  db_type: "sqlite",
  db_path: "",
  db_url: "",
  tablesText: "",
  enabled: true,
})

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

async function loadDatasources() {
  dsBusy.value = true
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

function clearAll() {
  error.value = null
  sqlExplain.value = ""
  sql.value = ""
  analysis.value = ""
  result.value = null
}

function cancel() {
  abortCtl.value?.abort()
  abortCtl.value = null
  busy.value = false
}

async function ask() {
  if (!question.value.trim()) return
  if (busy.value) cancel()

  clearAll()
  busy.value = true
  error.value = null

  const ctl = new AbortController()
  abortCtl.value = ctl

  try {
    await chatbiChatStream(
      { question: question.value.trim(), datasource_ids: selectedDatasourceIds.value, history: [] },
      {
        onEvent(ev) {
          if (ev.event === "chat") {
            analysis.value = (ev.data?.reply ?? "") as string
          } else if (ev.event === "sql_explain_delta") {
            sqlExplain.value += (ev.data?.delta ?? "") as string
          } else if (ev.event === "sql_explain") {
            sqlExplain.value = (ev.data?.sql_explain ?? sqlExplain.value) as string
          } else if (ev.event === "sql_delta") {
            sql.value += (ev.data?.delta ?? "") as string
          } else if (ev.event === "sql") {
            sql.value = (ev.data?.sql ?? sql.value) as string
          } else if (ev.event === "analysis_delta") {
            analysis.value += (ev.data?.delta ?? "") as string
          } else if (ev.event === "analysis") {
            analysis.value = (ev.data?.analysis ?? analysis.value) as string
          } else if (ev.event === "result") {
            result.value = ev.data?.result ?? null
          } else if (ev.event === "error") {
            error.value = (ev.data?.error ?? "查询失败") as string
          }
        },
        onError(err) {
          // ignored; the outer catch handles it
        },
      },
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

async function runSql() {
  if (!sql.value.trim()) return
  error.value = null
  busy.value = true
  try {
    const res = await chatbiRunSql({ sql: sql.value.trim(), datasource_ids: selectedDatasourceIds.value, question: question.value.trim() })
    result.value = res
    analysis.value = res?.analysis ?? analysis.value
  } catch (e: any) {
    if (_handleUnauthorized(e)) return
    error.value = _formatErr(e)
  } finally {
    busy.value = false
  }
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

function downloadCsv() {
  const data = result.value?.data
  if (!Array.isArray(data) || data.length === 0) return
  const cols = columns.value
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

function _splitTables(text: string): string[] {
  return (text ?? "")
    .split(/[,，\n]/g)
    .map((s) => s.trim())
    .filter(Boolean)
}

async function saveDatasource() {
  dsManageError.value = null
  dsSaveBusy.value = true
  try {
    const tables = _splitTables(dsForm.tablesText)
    await upsertChatbiDatasource({
      id: dsForm.id.trim(),
      name: dsForm.name.trim() || undefined,
      description: dsForm.description.trim() || undefined,
      db_type: dsForm.db_type,
      db_path: dsForm.db_type === "sqlite" ? (dsForm.db_path.trim() || undefined) : undefined,
      db_url: dsForm.db_type !== "sqlite" ? (dsForm.db_url.trim() || undefined) : undefined,
      tables,
      enabled: !!dsForm.enabled,
    })
    await loadDatasources()
    dsForm.id = ""
    dsForm.name = ""
    dsForm.description = ""
    dsForm.db_path = ""
    dsForm.db_url = ""
    dsForm.tablesText = ""
    dsForm.enabled = true
  } catch (e: any) {
    if (_handleUnauthorized(e)) return
    dsManageError.value = _formatErr(e)
  } finally {
    dsSaveBusy.value = false
  }
}

async function removeDatasource(id: string) {
  dsManageError.value = null
  dsSaveBusy.value = true
  try {
    await deleteChatbiDatasource(id)
    await loadDatasources()
  } catch (e: any) {
    if (_handleUnauthorized(e)) return
    dsManageError.value = _formatErr(e)
  } finally {
    dsSaveBusy.value = false
  }
}

onMounted(() => {
  loadDatasources()
})
</script>

<style scoped>
.chatbi {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.dsList {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.dsName {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resultBlock {
  border: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  border-radius: 12px;
  padding: 10px;
  background: var(--card, rgba(255, 255, 255, 0.03));
}

.pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 8px 0 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  line-height: 1.55;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
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

.tableTiny {
  font-size: 11px;
}

.th,
.td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  vertical-align: top;
  white-space: nowrap;
}
</style>
