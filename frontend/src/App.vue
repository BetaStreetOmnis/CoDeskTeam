<template>
  <div class="app" :class="[theme, vibe, densityClass, { authed: !!me }]">
    <div v-if="!authReady" class="splash">
      <div class="splashCard">
        <div class="logoBig">aistaff</div>
        <div class="subtle">正在连接服务…</div>
      </div>
    </div>

    <div v-else-if="!me" class="loginWrap">
      <div class="loginCard">
        <div class="loginBrand">
          <div class="logoBig">aistaff</div>
          <div class="subtle">AI 员工工作台</div>
        </div>

        <div class="loginMeta">
          <div class="pill" :class="apiOk ? 'ok' : 'bad'">
            <span class="dot" />
            <span>{{ apiOk ? "接口正常" : "接口异常" }}</span>
          </div>
          <button class="ghostBtn" type="button" @click="toggleTheme">
            {{ theme === "dark" ? "切换到浅色" : "切换到深色" }}
          </button>
        </div>

        <form v-if="setupRequired" class="form" @submit.prevent="submitSetup">
          <div class="fieldTitle">初始化管理员（首次使用）</div>
          <div class="row">
            <input v-model="setupTeamName" class="input" placeholder="团队名称" />
          </div>
          <div class="row">
            <input v-model="setupName" class="input" placeholder="你的名字" />
          </div>
          <div class="row">
            <input v-model="setupEmail" class="input" placeholder="邮箱" />
          </div>
          <div class="row">
            <input v-model="setupPassword" class="input" type="password" placeholder="密码（至少 6 位）" />
          </div>
          <div class="row">
            <button class="primaryBtn" :disabled="authBusy" type="submit">初始化并登录</button>
          </div>
          <div v-if="authError" class="error">{{ authError }}</div>
        </form>

	        <form v-else-if="pendingLoginTeamPick" class="form" @submit.prevent="confirmLoginTeamPick">
	          <div class="fieldTitle">选择团队</div>
	          <div class="subtle">首次登录请选择所属团队，之后可在菜单切换。</div>
	          <label class="select wide">
	            <span class="label">团队</span>
	            <select v-model.number="pendingLoginTeamId" :disabled="authBusy">
	              <option v-for="t in pendingLoginTeamPick.teams" :key="t.id" :value="t.id">{{ t.name }}（{{ t.role }}）</option>
	            </select>
	          </label>
	          <div class="row">
	            <button class="primaryBtn" :disabled="authBusy" type="submit">进入</button>
	            <button class="ghostBtn" :disabled="authBusy" type="button" @click="cancelLoginTeamPick">返回</button>
	          </div>
	          <div v-if="authError" class="error">{{ authError }}</div>
	        </form>

	        <form v-else-if="authMode === 'register'" class="form" @submit.prevent="submitRegister">
	          <div class="fieldTitle">注册（邀请码）</div>
	          <div class="subtle">需要团队管理员发放的邀请码。</div>
	          <label class="select wide">
	            <span class="label">团队</span>
	            <select v-model.number="registerTeamId" :disabled="authBusy || authTeamsBusy">
	              <option v-for="t in authTeams" :key="t.id" :value="t.id">{{ t.name }}</option>
	            </select>
	          </label>
	          <div v-if="authTeamsError" class="error">{{ authTeamsError }}</div>
	          <div class="row">
	            <input v-model="registerInviteToken" class="input" placeholder="邀请码" />
	          </div>
	          <div class="row">
	            <input v-model="registerName" class="input" placeholder="你的名字" />
	          </div>
	          <div class="row">
	            <input v-model="registerEmail" class="input" placeholder="邮箱" />
	          </div>
	          <div class="row">
	            <input v-model="registerPassword" class="input" type="password" placeholder="密码（至少 6 位）" />
	          </div>
	          <div class="row">
	            <input v-model="registerPassword2" class="input" type="password" placeholder="确认密码" />
	          </div>
	          <div class="row">
	            <button class="primaryBtn" :disabled="authBusy" type="submit">注册并登录</button>
	            <button class="ghostBtn" :disabled="authBusy" type="button" @click="authMode = 'login'; authError = null">返回登录</button>
	          </div>
	          <div v-if="authError" class="error">{{ authError }}</div>
	        </form>

	        <form v-else class="form" @submit.prevent="submitLogin">
	          <div class="fieldTitle">登录</div>
	          <div class="row">
	            <input v-model="loginEmail" class="input" placeholder="邮箱" />
	          </div>
	          <div class="row">
	            <input v-model="loginPassword" class="input" type="password" placeholder="密码" />
	          </div>
	          <div class="row">
	            <button class="primaryBtn" :disabled="authBusy" type="submit">登录</button>
	            <button class="ghostBtn" :disabled="authBusy" type="button" @click="authMode = 'register'; authError = null">邀请码注册</button>
	          </div>
	          <div v-if="authError" class="error">{{ authError }}</div>
	        </form>
	      </div>
	    </div>

    <template v-else>
      <header class="top">
        <div class="brand">
          <div class="logo">
            <span class="msIcon brandIcon" aria-hidden="true">note_stack</span>
            <span>aistaff</span>
          </div>
          <div class="tagline">AI 员工工作台</div>
        </div>

        <div class="topActions">
          <div class="pill" :class="apiOk ? 'ok' : 'bad'">
            <span class="dot" />
            <span>{{ apiOk ? "接口正常" : "接口异常" }}</span>
          </div>

          <div class="pill topUserPill">
            <span class="dot" />
            <span>{{ me.user.name }} · {{ me.active_team.name }}（{{ me.active_team.role }}）</span>
          </div>

          <div class="pill topProjectPill">
            <span class="dot" />
            <span>{{ activeWorkspaceLabel }} · {{ activeAgentProfile.name }} · {{ securityPresetLabel }}</span>
          </div>

          <button class="ghostBtn menuBtn iconBtn" type="button" @click="showTopMenu = true">
            <span class="msIcon btnIcon" aria-hidden="true">menu</span>
            <span>菜单</span>
          </button>

          <button class="ghostBtn iconBtn" type="button" @click="showTeamCenter = true; showTopMenu = false">
            <span class="msIcon btnIcon" aria-hidden="true">group</span>
            <span>团队</span>
          </button>

          <button class="ghostBtn iconBtn" type="button" @click="toggleTheme">
            <span class="msIcon btnIcon" aria-hidden="true">{{ theme === "dark" ? "light_mode" : "dark_mode" }}</span>
            <span>{{ theme === "dark" ? "浅色" : "深色" }}</span>
          </button>
        </div>
      </header>

      <div class="contextBar">
        <div class="contextItem">
          <span class="contextLabel">项目</span>
          <span class="contextValue">{{ activeWorkspaceLabel }}</span>
        </div>
        <div class="contextItem">
          <span class="contextLabel">模型</span>
          <span class="contextValue">{{ provider }} · {{ role }}</span>
        </div>
        <div class="contextItem">
          <span class="contextLabel">安全</span>
          <span class="contextValue">{{ securityPresetLabel }}</span>
        </div>
        <div class="contextItem">
          <span class="contextLabel">会话</span>
          <span class="contextValue mono">{{ sessionId ?? "new" }}</span>
        </div>
      </div>

      <div class="layout" :class="{ noLeft: !showLeft, noRight: !showRight, leftCollapsed: showLeft && leftRailCollapsed }">
        <aside v-if="showLeft" class="side sideShell" :class="{ collapsed: leftRailCollapsed }">
          <nav class="leftRail" aria-label="控制台分区">
            <button
              class="railBtn"
              :class="{ active: leftNavSection === 'workspace' }"
              type="button"
              title="工作台"
              @click="switchLeftNav('workspace')"
            >
              <span class="msIcon" aria-hidden="true">widgets</span>
            </button>
            <button
              class="railBtn"
              :class="{ active: leftNavSection === 'skills' }"
              type="button"
              title="技能"
              @click="switchLeftNav('skills')"
            >
              <span class="msIcon" aria-hidden="true">auto_awesome</span>
            </button>
            <button
              class="railBtn"
              :class="{ active: leftNavSection === 'history' }"
              type="button"
              title="历史"
              @click="switchLeftNav('history')"
            >
              <span class="msIcon" aria-hidden="true">history</span>
            </button>
            <button
              class="railBtn"
              :class="{ active: leftNavSection === 'session' }"
              type="button"
              title="运行"
              @click="switchLeftNav('session')"
            >
              <span class="msIcon" aria-hidden="true">forum</span>
            </button>
            <div class="railDivider" aria-hidden="true"></div>
            <button
              class="railBtn railToggle"
              type="button"
              :title="leftRailCollapsed ? '展开左栏' : '收起左栏'"
              @click="leftRailCollapsed = !leftRailCollapsed"
            >
              <span class="msIcon" aria-hidden="true">{{ leftRailCollapsed ? "right_panel_open" : "left_panel_close" }}</span>
            </button>
          </nav>

          <div v-show="!leftRailCollapsed" class="sideContent">
            <WorkspaceDomainPanel :ctx="appDomainCtx" />

            <HistoryDomainPanel :ctx="appDomainCtx" />

            <SessionSidebarPanel :ctx="appDomainCtx" />
          </div>
        </aside>

        <ChatbiMainDomain v-if="workspacePanel === 'chatbi'" :ctx="appDomainCtx" />
        <SessionMainDomain v-else :ctx="appDomainCtx" />
      </div>

      <TeamManagementDomain :ctx="appDomainCtx" />

      <HistoryModalDomain :ctx="appDomainCtx" />

    </template>

    <div v-if="toastText" class="toast" role="status" aria-live="polite">{{ toastText }}</div>
  </div>
</template>

<script setup lang="ts">
import DOMPurify from "dompurify"
import { marked } from "marked"
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue"
import {
  aiDraftTeamSkill,
	  authLogin,
	  authRegister,
	  authSetup,
	  authStatus,
	  listAuthTeams,
	  browserNavigate,
	  browserScreenshot,
	  browserStart,
	  chat,
  createTeamFeishuWebhook,
  createTeamProject,
  createTeamRequirement,
  createTeamSkill,
  deleteHistorySession,
  deleteTeamFeishuWebhook,
  deleteTeamProject,
  deleteTeamRequirement,
	  deleteTeamSkill,
	  discoverTeamProjects,
	  ensureTeamFeishuPreset,
	  exportTeamDbMarkdown,
	  getHistorySession,
	  getMe,
	  importTeamProjects,
	  listSkills,
  listTeamFeishuWebhooks,
  runSkill,
  setAuthToken,
  health,
  getFilePreview,
  getTeamProjectReadme,
  getTeamWorkspaceReadme,
  switchTeam,
  uploadImage,
  uploadFile,
  updateTeamFeishuWebhook,
  updateTeamProject,
  updateTeamRequirement,
  updateTeamSettings,
  updateTeamSkill,
} from "./api/index"
import { useTeamWorkspaceState } from "./composables/useTeamWorkspaceState"
import { useHistoryState } from "./composables/useHistoryState"
import WorkspaceDomainPanel from "./components/domains/WorkspaceDomainPanel.vue"
import HistoryDomainPanel from "./components/domains/HistoryDomainPanel.vue"
import SessionSidebarPanel from "./components/domains/SessionSidebarPanel.vue"
import SessionMainDomain from "./components/domains/SessionMainDomain.vue"
import ChatbiMainDomain from "./components/domains/ChatbiMainDomain.vue"
import TeamManagementDomain from "./components/domains/TeamManagementDomain.vue"
import HistoryModalDomain from "./components/domains/HistoryModalDomain.vue"
import type {
		  AuthResponse,
		  BuiltinSkill,
		  HistoryFileItem,
		  HistorySessionDetailResponse,
			  HistorySessionItem,
			  MeResponse,
			  PublicTeam,
			  TeamDbExport,
			  TeamFeishuWebhook,
			  TeamProject,
			  TeamRequirement,
			  TeamSettings,
		  TeamSkill,
		} from "./api/index"

	type Theme = "light" | "dark"
	type Provider = "openai" | "mock" | "opencode" | "nanobot" | "codex"
  type Vibe = "toc" | "pro" | "notebook"
  type RoleMode = "general" | "engineer"
  type SecurityPreset = "safe" | "standard" | "power" | "custom"
  type DensityMode = "auto" | "compact" | "normal" | "comfortable"
  type LeftNavSection = "workspace" | "skills" | "history" | "session"
  type WorkspacePanel = "projects" | "requirements" | "capabilities" | "browser" | "chatbi"
  type FeishuManageMode = "global" | "single"
  type AgentProfileId = "custom" | "assistant" | "engineer" | "writer" | "prototype" | "research"
	type UiAttachment = {
	  kind: "image" | "file"
	  url: string
	  filename?: string
	  file_id?: string
	  content_type?: string
	  size_bytes?: number
	}
	type UiMessage = { id: string; role: "user" | "assistant"; content: string; ts: number; attachments?: UiAttachment[] }
	type AgentProfilePreset = {
	  id: Exclude<AgentProfileId, "custom">
	  name: string
	  description: string
	  provider: Provider
	  role: RoleMode
	  vibe: Vibe
	  security: SecurityPreset
	}


marked.use({ gfm: true, breaks: true })

const apiOk = ref(false)
const sending = ref(false)
const docsBusy = ref(false)

const authReady = ref(false)
const authBusy = ref(false)
const authError = ref<string | null>(null)
const setupRequired = ref(false)
const me = ref<MeResponse | null>(null)

const authToken = ref<string | null>(localStorage.getItem("aistaff_token"))
setAuthToken(authToken.value)

const authMode = ref<"login" | "register">("login")

const authTeamsBusy = ref(false)
const authTeamsError = ref<string | null>(null)
const authTeams = ref<PublicTeam[]>([])
const registerTeamId = ref<number>(0)

const loginEmail = ref("")
const loginPassword = ref("")

const registerInviteToken = ref("")
const registerName = ref("")
const registerEmail = ref("")
const registerPassword = ref("")
const registerPassword2 = ref("")

async function refreshAuthTeams() {
  authTeamsBusy.value = true
  authTeamsError.value = null
  try {
    const teams = await listAuthTeams()
    authTeams.value = Array.isArray(teams) ? teams : []
    if (!registerTeamId.value && authTeams.value.length) registerTeamId.value = authTeams.value[0]?.id || 0
    if (registerTeamId.value && !authTeams.value.some((t) => t.id === registerTeamId.value)) {
      registerTeamId.value = authTeams.value[0]?.id || 0
    }
  } catch (e: any) {
    authTeamsError.value = formatAxiosError(e)
    authTeams.value = []
  } finally {
    authTeamsBusy.value = false
  }
}

watch(authMode, (mode) => {
  if (mode === "register") refreshAuthTeams()
})

const TEAM_PREF_KEY = "aistaff_team_pref_v1"
const TEAM_ONBOARDED_KEY = "aistaff_team_onboarded_v1"

function normalizeEmail(value: string): string {
  return String(value || "").trim().toLowerCase()
}

function readLocalJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return fallback
    const parsed = JSON.parse(raw)
    return parsed as T
  } catch {
    return fallback
  }
}

function writeLocalJson(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // ignore
  }
}

function getLastTeamIdForEmail(email: string): number | null {
  const key = normalizeEmail(email)
  if (!key) return null
  const data = readLocalJson<Record<string, unknown>>(TEAM_PREF_KEY, {})
  const v = (data || {})[key]
  const n = Number(v)
  if (!Number.isFinite(n) || n <= 0) return null
  return Math.floor(n)
}

function setLastTeamIdForEmail(email: string, teamId: number) {
  const key = normalizeEmail(email)
  const id = Number(teamId)
  if (!key || !Number.isFinite(id) || id <= 0) return
  const data = readLocalJson<Record<string, unknown>>(TEAM_PREF_KEY, {})
  writeLocalJson(TEAM_PREF_KEY, { ...(data || {}), [key]: Math.floor(id) })
}

function clearLastTeamIdForEmail(email: string) {
  const key = normalizeEmail(email)
  if (!key) return
  const data = readLocalJson<Record<string, unknown>>(TEAM_PREF_KEY, {})
  if (!data || typeof data !== "object" || Array.isArray(data)) return
  if (!(key in data)) return
  const next = { ...(data as Record<string, unknown>) }
  delete next[key]
  writeLocalJson(TEAM_PREF_KEY, next)
}

function isTeamOnboarded(email: string): boolean {
  const key = normalizeEmail(email)
  if (!key) return false
  const data = readLocalJson<Record<string, unknown>>(TEAM_ONBOARDED_KEY, {})
  return !!(data || {})[key]
}

function markTeamOnboarded(email: string) {
  const key = normalizeEmail(email)
  if (!key) return
  const data = readLocalJson<Record<string, unknown>>(TEAM_ONBOARDED_KEY, {})
  writeLocalJson(TEAM_ONBOARDED_KEY, { ...(data || {}), [key]: true })
}

const pendingLoginTeamPick = ref<AuthResponse | null>(null)
const pendingLoginTeamId = ref<number>(0)

const setupTeamName = ref("我的团队")
const setupName = ref("")
const setupEmail = ref("")
const setupPassword = ref("")

const activeTeamId = ref<number | null>(null)

const theme = ref<Theme>(localStorage.getItem("aistaff_theme") === "dark" ? "dark" : "light")
watch(theme, (t) => localStorage.setItem("aistaff_theme", t))

const storedVibe = localStorage.getItem("aistaff_vibe")
const vibe = ref<Vibe>(
  storedVibe === "pro" || storedVibe === "toc" || storedVibe === "notebook" ? (storedVibe === "notebook" ? "pro" : storedVibe) : "pro",
)
watch(vibe, (v) => localStorage.setItem("aistaff_vibe", v))

const storedDensityMode = localStorage.getItem("aistaff_density_mode")
const densityMode = ref<DensityMode>(
  storedDensityMode === "compact" || storedDensityMode === "normal" || storedDensityMode === "comfortable" || storedDensityMode === "auto"
    ? storedDensityMode
    : "auto",
)
watch(densityMode, (v) => localStorage.setItem("aistaff_density_mode", v))

const viewportWidth = ref(typeof window !== "undefined" ? window.innerWidth : 1440)
const viewportHeight = ref(typeof window !== "undefined" ? window.innerHeight : 900)

function refreshViewportSize() {
  viewportWidth.value = window.innerWidth
  viewportHeight.value = window.innerHeight
}

const autoDensity = computed<Exclude<DensityMode, "auto">>(() => {
  const width = viewportWidth.value
  const height = viewportHeight.value
  if (height <= 820 || width <= 1366) return "compact"
  if (height >= 1000 && width >= 1920) return "comfortable"
  return "normal"
})

const effectiveDensity = computed<Exclude<DensityMode, "auto">>(() =>
  densityMode.value === "auto" ? autoDensity.value : densityMode.value,
)
const densityClass = computed(() => `density-${effectiveDensity.value}`)
const densityLabel = computed(() => {
  if (densityMode.value === "auto") {
    if (effectiveDensity.value === "compact") return "自动（当前紧凑）"
    if (effectiveDensity.value === "comfortable") return "自动（当前舒展）"
    return "自动（当前标准）"
  }
  if (densityMode.value === "compact") return "紧凑"
  if (densityMode.value === "comfortable") return "舒展"
  return "标准"
})

const storedProvider = localStorage.getItem("aistaff_provider")
const provider = ref<Provider>(
  storedProvider === "openai" || storedProvider === "opencode" || storedProvider === "nanobot" || storedProvider === "codex"
    ? storedProvider
    : "opencode",
)
watch(provider, (p) => {
  localStorage.setItem("aistaff_provider", p)
  if (p !== "codex") enableDangerous.value = false
})

const role = ref<RoleMode>(localStorage.getItem("aistaff_role") === "engineer" ? "engineer" : "general")
watch(role, (r) => localStorage.setItem("aistaff_role", r))

const storedSecurityPreset = localStorage.getItem("aistaff_security_preset")
const normalizedStoredPreset =
  storedSecurityPreset === "safe" ||
  storedSecurityPreset === "standard" ||
  storedSecurityPreset === "power" ||
  storedSecurityPreset === "custom"
    ? storedSecurityPreset
    : null
const storedEnableShell = localStorage.getItem("aistaff_enable_shell")
const storedEnableWrite = localStorage.getItem("aistaff_enable_write")
const storedEnableBrowser = localStorage.getItem("aistaff_enable_browser")
const shouldSeedDangerous =
  !normalizedStoredPreset && storedEnableShell === null && storedEnableWrite === null && storedEnableBrowser === null

const enableShell = ref(shouldSeedDangerous ? true : storedEnableShell === "1")
const enableWrite = ref(shouldSeedDangerous ? true : storedEnableWrite === "1")
const enableBrowser = ref(shouldSeedDangerous ? false : storedEnableBrowser === "1")
watch(enableShell, (v) => localStorage.setItem("aistaff_enable_shell", v ? "1" : "0"), { immediate: true })
watch(enableWrite, (v) => localStorage.setItem("aistaff_enable_write", v ? "1" : "0"), { immediate: true })
watch(enableBrowser, (v) => localStorage.setItem("aistaff_enable_browser", v ? "1" : "0"), { immediate: true })

const storedDangerous = localStorage.getItem("aistaff_codex_dangerous")
const enableDangerous = ref(storedDangerous === "1")
watch(enableDangerous, (v) => localStorage.setItem("aistaff_codex_dangerous", v ? "1" : "0"))
const storedReasoning = localStorage.getItem("aistaff_reasoning_summary")
const showReasoning = ref(storedReasoning !== "0")
watch(showReasoning, (v) => localStorage.setItem("aistaff_reasoning_summary", v ? "1" : "0"))
const codexAutoToolsApplied = ref(localStorage.getItem("aistaff_codex_auto_tools") === "1")
watch(codexAutoToolsApplied, (v) => localStorage.setItem("aistaff_codex_auto_tools", v ? "1" : "0"))

const sendingElapsed = ref(0)
let sendingTimer: number | null = null
const sendingStartedAt = ref<number | null>(null)
const sendAbortController = ref<AbortController | null>(null)
watch(sending, (active) => {
  if (active) {
    sendingStartedAt.value = Date.now()
    sendingElapsed.value = 0
    if (sendingTimer) window.clearInterval(sendingTimer)
    sendingTimer = window.setInterval(() => {
      if (!sendingStartedAt.value) return
      sendingElapsed.value = Math.floor((Date.now() - sendingStartedAt.value) / 1000)
    }, 1000)
    return
  }
  if (sendingTimer) {
    window.clearInterval(sendingTimer)
    sendingTimer = null
  }
  sendingStartedAt.value = null
  sendingElapsed.value = 0
})

const securityPreset = ref<SecurityPreset>(
  normalizedStoredPreset ?? "custom",
)
watch(
  securityPreset,
  (preset) => {
    localStorage.setItem("aistaff_security_preset", preset)
    if (preset === "safe") {
      enableShell.value = false
      enableWrite.value = false
      enableBrowser.value = false
      enableDangerous.value = false
      return
    }
    if (preset === "standard") {
      enableShell.value = false
      enableWrite.value = true
      enableBrowser.value = false
      enableDangerous.value = false
      return
    }
    if (preset === "power") {
      enableShell.value = true
      enableWrite.value = true
      enableBrowser.value = true
      enableDangerous.value = false
    }
  },
  { immediate: true },
)

const leftNavSection = ref<LeftNavSection>(
  localStorage.getItem("aistaff_left_nav") === "skills"
    ? "skills"
    : localStorage.getItem("aistaff_left_nav") === "history"
      ? "history"
      : localStorage.getItem("aistaff_left_nav") === "session"
        ? "session"
        : "workspace",
)
watch(leftNavSection, (v) => localStorage.setItem("aistaff_left_nav", v))

const leftRailCollapsed = ref(localStorage.getItem("aistaff_left_collapsed") === "1")
watch(leftRailCollapsed, (v) => localStorage.setItem("aistaff_left_collapsed", v ? "1" : "0"))

function switchLeftNav(section: LeftNavSection) {
  leftNavSection.value = section
  if (leftRailCollapsed.value) leftRailCollapsed.value = false
}

const storedWorkspacePanel = localStorage.getItem("aistaff_workspace_panel")
const workspacePanel = ref<WorkspacePanel>(
  storedWorkspacePanel === "projects" ||
    storedWorkspacePanel === "requirements" ||
    storedWorkspacePanel === "capabilities" ||
    storedWorkspacePanel === "browser" ||
    storedWorkspacePanel === "chatbi"
    ? storedWorkspacePanel
    : "requirements",
)
watch(workspacePanel, (v) => localStorage.setItem("aistaff_workspace_panel", v))

const agentProfiles: AgentProfilePreset[] = [
  {
    id: "assistant",
    name: "默认助理",
    description: "日常任务，稳健优先",
    provider: "opencode",
    role: "general",
    vibe: "pro",
    security: "safe",
  },
  {
    id: "engineer",
    name: "工程模式",
    description: "代码改造，能力全开",
    provider: "opencode",
    role: "engineer",
    vibe: "pro",
    security: "power",
  },
  {
    id: "writer",
    name: "文档模式",
    description: "文档/报价/PPT 生成",
    provider: "openai",
    role: "general",
    vibe: "pro",
    security: "standard",
  },
  {
    id: "prototype",
    name: "原型模式",
    description: "快速页面与原型产物",
    provider: "openai",
    role: "engineer",
    vibe: "pro",
    security: "standard",
  },
  {
    id: "research",
    name: "研究模式",
    description: "信息整理，最小权限",
    provider: "openai",
    role: "general",
    vibe: "pro",
    security: "safe",
  },
]

const storedProfile = localStorage.getItem("aistaff_agent_profile")
const selectedAgentProfileId = ref<AgentProfileId>(
  storedProfile === "assistant" ||
    storedProfile === "engineer" ||
    storedProfile === "writer" ||
    storedProfile === "prototype" ||
    storedProfile === "research" ||
    storedProfile === "custom"
    ? storedProfile
    : "custom",
)
watch(selectedAgentProfileId, (v) => localStorage.setItem("aistaff_agent_profile", v))

function applyAgentProfile(profileId: AgentProfileId) {
  selectedAgentProfileId.value = profileId
  if (profileId === "custom") return
  const profile = agentProfiles.find((p) => p.id === profileId)
  if (!profile) return
  provider.value = profile.provider
  role.value = profile.role
  vibe.value = profile.vibe
  securityPreset.value = profile.security
}

const activeAgentProfile = computed(() => {
  if (selectedAgentProfileId.value === "custom") {
    return { id: "custom" as const, name: "自定义", description: "手动配置当前会话" }
  }
  return (
    agentProfiles.find((p) => p.id === selectedAgentProfileId.value) ?? {
      id: "custom" as const,
      name: "自定义",
      description: "手动配置当前会话",
    }
  )
})
watch([provider, role, vibe, securityPreset], () => {
  if (selectedAgentProfileId.value === "custom") return
  const profile = agentProfiles.find((p) => p.id === selectedAgentProfileId.value)
  if (!profile) {
    selectedAgentProfileId.value = "custom"
    return
  }
  if (
    profile.provider !== provider.value ||
    profile.role !== role.value ||
    profile.vibe !== vibe.value ||
    profile.security !== securityPreset.value
  ) {
    selectedAgentProfileId.value = "custom"
  }
})
const securityPresetLabel = computed(() => {
  let label = "安全"
  if (securityPreset.value === "power") label = "高权限"
  else if (securityPreset.value === "standard") label = "标准"
  else if (securityPreset.value === "custom") label = "自定义"
  if (provider.value === "codex" && enableDangerous.value) return `${label} · 无沙箱`
  return label
})
const dangerousTogglesLocked = computed(() => !canEditTeamSkills.value || securityPreset.value !== "custom")
const dangerousBypassLocked = computed(
  () => !canEditTeamSkills.value || provider.value !== "codex" || securityPreset.value !== "custom",
)
const effectiveDangerous = computed(() => enableDangerous.value && !dangerousBypassLocked.value)

function cloneSkillPayload<T>(payload: T): T {
  try {
    if (typeof structuredClone === "function") return structuredClone(payload)
  } catch {
    // ignore
  }
  try {
    return JSON.parse(JSON.stringify(payload)) as T
  } catch {
    return payload
  }
}

const skills = ref<BuiltinSkill[]>([])
const selectedSkillId = ref("")
const skillPayloadById = ref<Record<string, unknown>>({})
const skillDownloadById = ref<Record<string, string | null>>({})
const skillError = ref<string | null>(null)
const selectedSkill = computed(() => skills.value.find((s) => s.id === selectedSkillId.value) ?? null)

const selectedSkillPayload = computed<unknown>({
  get() {
    const skill = selectedSkill.value
    if (!skill) return {}
    return skillPayloadById.value[skill.id] ?? cloneSkillPayload(skill.default_payload ?? {})
  },
  set(next) {
    const skill = selectedSkill.value
    if (!skill) return
    skillPayloadById.value = { ...skillPayloadById.value, [skill.id]: next }
  },
})

const selectedSkillPayloadJson = computed(() => {
  try {
    return JSON.stringify(selectedSkillPayload.value ?? {}, null, 2)
  } catch {
    return "{}"
  }
})

function _payloadText(value: unknown): string {
  return typeof value === "string" ? value.trim() : ""
}

function _payloadBullets(value: unknown): string[] {
  const items: unknown[] = Array.isArray(value) ? value : []
  return items.map((item) => String(item ?? "").trim()).filter((item) => !!item)
}

function payloadToMarkdown(skill: BuiltinSkill | null, payload: unknown): string {
  if (!skill || !payload || typeof payload !== "object") return ""
  const data = payload as Record<string, unknown>

  if (skill.endpoint === "/api/docs/ppt") {
    const title = _payloadText(data.title) || "演示文稿"
    const slidesRaw: unknown[] = Array.isArray(data.slides) ? (data.slides as unknown[]) : []
    const lines: string[] = [`# ${title}`, ""]

    slidesRaw.forEach((slide, idx) => {
      const s = (slide ?? {}) as Record<string, unknown>
      const slideTitle = _payloadText(s.title) || `第 ${idx + 1} 页`
      lines.push(`## ${idx + 1}. ${slideTitle}`)
      const bullets = _payloadBullets(s.bullets)
      if (!bullets.length) lines.push("- （待补充）")
      else bullets.forEach((bullet) => lines.push(`- ${bullet}`))
      lines.push("")
    })

    return lines.join("\n").trim()
  }

  if (skill.endpoint === "/api/docs/quote" || skill.endpoint === "/api/docs/quote-xlsx") {
    const seller = _payloadText(data.seller) || "供方"
    const buyer = _payloadText(data.buyer) || "需方"
    const currency = _payloadText(data.currency) || "CNY"
    const itemsRaw: unknown[] = Array.isArray(data.items) ? (data.items as unknown[]) : []

    const lines: string[] = [
      `# 报价单（${currency}）`,
      "",
      `- 供方：${seller}`,
      `- 需方：${buyer}`,
      "",
      "| 名称 | 数量 | 单位 | 单价 |",
      "|---|---:|---|---:|",
    ]

    if (!itemsRaw.length) {
      lines.push("| （待补充） | 0 | 项 | 0 |")
    } else {
      for (const item of itemsRaw) {
        const row = (item ?? {}) as Record<string, unknown>
        lines.push(
          `| ${_payloadText(row.name) || "未命名"} | ${String(row.quantity ?? 0)} | ${_payloadText(row.unit) || "项"} | ${String(row.unit_price ?? 0)} |`,
        )
      }
    }

    const note = _payloadText(data.note)
    if (note) lines.push("", `> 备注：${note}`)
    return lines.join("\n")
  }

  if (skill.endpoint === "/api/prototype/generate") {
    const name = _payloadText(data.project_name) || "产品原型"
    const pagesRaw: unknown[] = Array.isArray(data.pages) ? (data.pages as unknown[]) : []
    const lines: string[] = [`# 原型：${name}`, "", "## 页面清单"]

    if (!pagesRaw.length) {
      lines.push("- （待补充）")
    } else {
      for (const page of pagesRaw) {
        const item = (page ?? {}) as Record<string, unknown>
        const title = _payloadText(item.title) || "未命名页面"
        const desc = _payloadText(item.description)
        lines.push(`- ${title}${desc ? `：${desc}` : ""}`)
      }
    }

    return lines.join("\n")
  }

  if (skill.endpoint === "/api/docs/inspection" || skill.endpoint === "/api/docs/inspection-xlsx") {
    const title = _payloadText(data.title) || "报检单"
    const lines: string[] = [`# ${title}`, ""]
    const sections = ["basic_info", "device_info", "network_info", "inspection_info", "conclusion", "signatures"]

    for (const key of sections) {
      const raw = data[key]
      if (!raw || typeof raw !== "object") continue
      const row = raw as Record<string, unknown>
      const entries = Object.entries(row).filter(([, value]) => _payloadText(value).length > 0)
      if (!entries.length) continue
      lines.push(`## ${key}`)
      entries.forEach(([field, value]) => lines.push(`- ${field}: ${_payloadText(value)}`))
      lines.push("")
    }

    const inspectionItemsRaw: unknown[] = Array.isArray(data.inspection_items) ? (data.inspection_items as unknown[]) : []
    if (inspectionItemsRaw.length) {
      lines.push("## inspection_items")
      inspectionItemsRaw.forEach((item, idx) => {
        const row = (item ?? {}) as Record<string, unknown>
        lines.push(`- ${idx + 1}. ${_payloadText(row.name) || "检查项"}：${_payloadText(row.result) || ""}`)
      })
    }

    return lines.join("\n").trim()
  }

  return ""
}

const selectedSkillPayloadMarkdown = computed(() => payloadToMarkdown(selectedSkill.value, selectedSkillPayload.value))

const feishuManageMode = ref<FeishuManageMode>(
  localStorage.getItem("aistaff_feishu_manage_mode") === "single" ? "single" : "global",
)
watch(feishuManageMode, (v) => localStorage.setItem("aistaff_feishu_manage_mode", v))

const teamFeishuStats = computed(() => {
  const total = teamFeishuWebhooks.value.length
  const enabled = teamFeishuWebhooks.value.filter((item) => !!item.enabled).length
  return { total, enabled, disabled: Math.max(0, total - enabled) }
})

const sessionId = ref<string | undefined>(undefined)
const input = ref("")
const messages = ref<UiMessage[]>([])
const lastEvents = ref<any[]>([])
const eventsByMessageId = ref<Record<string, any[]>>({})
const lastStructuredTrace = computed(() => structuredTrace(lastEvents.value))
const showTrace = ref(localStorage.getItem("aistaff_show_trace") === "1")
watch(showTrace, (v) => localStorage.setItem("aistaff_show_trace", v ? "1" : "0"))

const showLeft = ref(localStorage.getItem("aistaff_show_left") !== "0")
watch(showLeft, (v) => localStorage.setItem("aistaff_show_left", v ? "1" : "0"))
const showRight = ref(localStorage.getItem("aistaff_show_right") !== "0")
watch(showRight, (v) => localStorage.setItem("aistaff_show_right", v ? "1" : "0"))

const showTopMenu = ref(false)
const showTeamCenter = ref(false)

const toastText = ref<string | null>(null)
let _toastTimer: number | undefined
function showToast(text: string) {
  toastText.value = text
  if (_toastTimer) window.clearTimeout(_toastTimer)
  _toastTimer = window.setTimeout(() => {
    toastText.value = null
  }, 2200)
}

function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      reject(new Error(`${label} timeout after ${ms}ms`))
    }, ms)
    promise
      .then((value) => {
        window.clearTimeout(timer)
        resolve(value)
      })
      .catch((err) => {
        window.clearTimeout(timer)
        reject(err)
      })
  })
}

	type PendingImage = { file_id: string; url: string; filename: string; content_type: string }
	const imagePickerRef = ref<HTMLInputElement | null>(null)
	const filePickerRef = ref<HTMLInputElement | null>(null)
  const composerInputRef = ref<HTMLTextAreaElement | null>(null)
	const pendingImages = ref<PendingImage[]>([])
	type PendingFile = { file_id: string; url: string; filename: string; content_type: string; size_bytes: number }
	const pendingFiles = ref<PendingFile[]>([])
	const uploadingImages = ref(false)
	const uploadingFiles = ref(false)
	const uploadError = ref<string | null>(null)

const browserUrl = ref("https://example.com")
const browserImg = ref<string | null>(null)
const browserError = ref<string | null>(null)

const workspaceState = useTeamWorkspaceState({
  me,
  formatError: formatAxiosError,
  handleUnauthorized,
  showToast,
})

const {
  teamSkills,
  teamSkillsBusy,
  teamSkillsError,
  selectedTeamSkillId,
  teamSkillForm,
  teamProjects,
  teamProjectsBusy,
  teamProjectsError,
  projectSearch,
  activeProjectId,
  previousProjectId,
  showProjectModal,
  selectedTeamProjectId,
  teamProjectForm,
  projectTreeById,
  projectTreeBusyById,
  projectTreeErrorById,
  projectTreeExpandedById,
  teamSettings,
  teamSettingsBusy,
  teamSettingsError,
  teamWorkspaceDraft,
  teamFeishuWebhooks,
  teamFeishuBusy,
  teamFeishuError,
  selectedTeamFeishuId,
  teamFeishuForm,
  teamRequirements,
  teamRequirementsBusy,
  teamRequirementsError,
  selectedTeamRequirementId,
  requirementSearch,
  requirementStatusFilter,
  requirementPriorityFilter,
  teamRequirementForm,
  filteredTeamProjects,
  filteredTeamRequirements,
  requirementStats,
  canEditTeamSkills,
  canEditTeamProjects,
  canEditTeamFeishu,
  canEditTeamRequirements,
  activeProject,
  selectedTeamFeishu,
  selectedTeamRequirement,
  teamWorkspacePath,
  activeWorkspaceLabel,
  activeWorkspacePath,
  projectNameFromId,
  requirementStatusLabel,
  requirementPriorityLabel,
  resetRequirementFilters,
  toggleProjectTree: toggleProjectTreeCore,
  flattenProjectTree,
  toggleProjectTreeFolder,
  isProjectTreeFolderOpen,
  isProjectTreeFolderBusy,
  refreshTeamSkills,
  refreshTeamSettings,
  refreshTeamProjects,
  refreshTeamRequirements,
  refreshWorkspace,
} = workspaceState

const teamDbExportBusy = ref(false)
const teamDbExportError = ref<string | null>(null)
const teamDbExport = ref<TeamDbExport | null>(null)

watch(canEditTeamSkills, (canEdit) => {
  if (!canEdit) enableDangerous.value = false
})

watch([provider, canEditTeamSkills], () => {
  if (provider.value !== "codex") return
  if (!canEditTeamSkills.value) return
  if (codexAutoToolsApplied.value) return
  securityPreset.value = "custom"
  enableShell.value = true
  enableWrite.value = true
  codexAutoToolsApplied.value = true
})

const historyState = useHistoryState({
  me,
  activeProjectId,
  projectNameFromId,
  formatError: formatAxiosError,
  handleUnauthorized,
})

const {
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
} = historyState

const chatBodyRef = ref<HTMLDivElement | null>(null)
	const draggingFiles = ref(false)
  const isNearBottom = ref(true)
	let _dragDepth = 0

	function _dragHasFiles(e: DragEvent): boolean {
	  const dt = e.dataTransfer
	  if (!dt) return false
	  const types = Array.from(dt.types ?? [])
	  if (types.includes("Files")) return true
	  const items = Array.from(dt.items ?? [])
	  return items.some((it) => it.kind === "file")
	}

	function onChatDragEnter(e: DragEvent) {
	  if (!_dragHasFiles(e)) return
	  e.preventDefault()
	  _dragDepth += 1
	  draggingFiles.value = true
	}

	function onChatDragOver(e: DragEvent) {
	  if (!_dragHasFiles(e)) return
	  e.preventDefault()
	  draggingFiles.value = true
	}

	function onChatDragLeave(e: DragEvent) {
	  if (!draggingFiles.value) return
	  e.preventDefault()
	  _dragDepth = Math.max(0, _dragDepth - 1)
	  if (_dragDepth === 0) draggingFiles.value = false
	}

	async function onChatDrop(e: DragEvent) {
	  if (!_dragHasFiles(e)) return
	  e.preventDefault()
	  e.stopPropagation()
	  _dragDepth = 0
	  draggingFiles.value = false
	  await onComposerDrop(e)
	}

  function _computeIsNearBottom(el: HTMLElement): boolean {
    const threshold = 180
    return el.scrollHeight - el.scrollTop - el.clientHeight < threshold
  }

  function onChatBodyScroll() {
    const el = chatBodyRef.value
    if (!el) return
    isNearBottom.value = _computeIsNearBottom(el)
  }

  function scrollToBottom(smooth = false) {
    const el = chatBodyRef.value
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" })
    isNearBottom.value = true
  }

  const showScrollToBottom = computed(() => !isNearBottom.value && messages.value.length > 0)

	watch(
	  () => messages.value.length,
	  async () => {
	    await nextTick()
      if (isNearBottom.value) scrollToBottom(true)
	  },
	)

function formatTime(ts: number): string {
  const d = new Date(ts)
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

function formatIsoTime(iso: string): string {
  const value = String(iso || "").trim()
  if (!value) return ""
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString([], { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
}

function formatBytes(bytes: number): string {
  const n = Number(bytes ?? 0)
  if (!Number.isFinite(n) || n <= 0) return "0 B"
  const units = ["B", "KB", "MB", "GB"]
  let v = n
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function renderMarkdown(text: string): string {
  const raw = marked.parse(text ?? "") as string
  return DOMPurify.sanitize(raw)
}

type ReasoningParts = { summary: string | null; answer: string }
const reasoningPartsCacheByText = new Map<string, ReasoningParts>()
const reasoningPartsCacheById = new Map<string, ReasoningParts>()

function splitReasoningContent(text: string): ReasoningParts {
  const raw = String(text ?? "").trim()
  if (!raw) return { summary: null, answer: "" }
  const cached = reasoningPartsCacheByText.get(raw)
  if (cached) return cached

  const patterns = [
    /(?:^|\n)\s*(思路摘要|Thoughts?|Summary)\s*[:：]\s*([\s\S]*?)\n\s*(最终回答|Answer|Final)\s*[:：]\s*([\s\S]*)$/i,
    /(?:^|\n)\s*(思路摘要|Thoughts?|Summary)\s*\n([\s\S]*?)\n\s*(最终回答|Answer|Final)\s*\n([\s\S]*)$/i,
  ]

  for (const re of patterns) {
    const m = raw.match(re)
    if (m) {
      const summary = String(m[2] || "").trim()
      const answer = String(m[4] || "").trim()
      if (summary) {
        const out = { summary, answer }
        if (reasoningPartsCacheByText.size > 240) reasoningPartsCacheByText.clear()
        reasoningPartsCacheByText.set(raw, out)
        return out
      }
    }
  }

  const out = { summary: null, answer: raw }
  if (reasoningPartsCacheByText.size > 240) reasoningPartsCacheByText.clear()
  reasoningPartsCacheByText.set(raw, out)
  return out
}

function assistantParts(m: UiMessage): ReasoningParts {
  const key = m.id
  const cached = reasoningPartsCacheById.get(key)
  if (cached) return cached
  const out = splitReasoningContent(m.content)
  if (reasoningPartsCacheById.size > 240) reasoningPartsCacheById.clear()
  reasoningPartsCacheById.set(key, out)
  return out
}

async function applyQuickPrompt(text: string) {
  input.value = text
  await nextTick()
  composerInputRef.value?.focus()
  try {
    composerInputRef.value?.setSelectionRange(input.value.length, input.value.length)
  } catch {
    // ignore
  }
}

type DownloadLink = { relative: string; absolute: string }
type PptSlidePreview = { title: string; bullets: string[] }
type PptPreview = { title: string; slides: PptSlidePreview[]; coverImageUrl?: string; slideImageUrls?: string[]; downloadUrl?: string }
type QuoteItemPreview = { name: string; quantity: number; unit_price: number; unit?: string }
type QuotePreview = {
  kind: "docx" | "xlsx"
  seller: string
  buyer: string
  currency: string
  items: QuoteItemPreview[]
  note?: string
  total: number
}
type ProtoPagePreview = { title: string; description?: string }
type ProtoPreview = { project_name: string; pages: ProtoPagePreview[]; preview_url: string }
type SheetPreview = { filename: string; downloadUrl: string; previewUrl?: string; pageImageUrls?: string[] }
type DocPreview = { kind: "pdf" | "docx"; title: string; pageImageUrls: string[]; downloadUrl?: string; previewUrl?: string }
type ReadmePreview = { projectId: number; title: string; relPath?: string | null; content: string; truncated: boolean; sourceLabel: string }

const _TRAILING_PUNCT_RE = /[),.;:!?'"，。；：！？）】》』”’\]]+$/

function _trimTrailingPunctuation(url: string): string {
  let out = url
  while (out && _TRAILING_PUNCT_RE.test(out)) out = out.slice(0, -1)
  return out
}

function toAbsoluteUrl(url: string): string {
  const value = (url || "").trim()
  if (!value) return value
  try {
    return new URL(value, window.location.origin).toString()
  } catch {
    return value
  }
}

function extractDownloadLinks(text: string): DownloadLink[] {
  const matches =
    (text || "").match(/(?:https?:\/\/[^\s]*?)?\/api\/files\/[A-Za-z0-9][A-Za-z0-9._-]{0,199}\?token=[^\s]+/g) ??
    []
  const seen = new Set<string>()
  const out: DownloadLink[] = []
  for (const m of matches) {
    const relative = _trimTrailingPunctuation(m)
    if (!relative) continue
    const absolute = toAbsoluteUrl(relative)
    if (seen.has(absolute)) continue
    seen.add(absolute)
    out.push({ relative, absolute })
  }
  return out
}

const _FILE_ID_RE = /\/api\/files\/([^?]+)/i
const previewedFileIds = new Set<string>()

function extractFileIdFromDownload(url: string): string | null {
  const match = String(url || "").match(_FILE_ID_RE)
  if (!match) return null
  const fileId = (match[1] || "").trim()
  return fileId || null
}

function maybeSetActivePreview(kind: MessagePreviewKind, messageId: string) {
  const current = activePreview.value
  if (!current || current.kind === "files") {
    activePreview.value = { kind, messageId }
  }
}

async function hydrateFilePreviewsFromText(messageId: string, text: string) {
  const links = extractDownloadLinks(text)
  if (!links.length) return
  for (const link of links) {
    const fileId = extractFileIdFromDownload(link.relative)
    if (!fileId) continue
    if (previewedFileIds.has(fileId)) continue
    previewedFileIds.add(fileId)
    try {
      const res = await getFilePreview(fileId)
      const kind = String(res?.kind || "")
      if (kind === "pptx") {
        const previewImages = Array.isArray(res.preview_images)
          ? res.preview_images.map((u) => toAbsoluteUrl(String(u || ""))).filter((u) => !!u)
          : []
        const preview: PptPreview = {
          title: fileId,
          slides: [],
          coverImageUrl: previewImages[0],
          slideImageUrls: previewImages,
          downloadUrl: toAbsoluteUrl(res.download_url),
        }
        pptPreviewByMessageId.value = { ...pptPreviewByMessageId.value, [messageId]: preview }
        maybeSetActivePreview("ppt", messageId)
        continue
      }

      if (kind === "pdf" || kind === "docx") {
        const previewImages = Array.isArray(res.preview_images)
          ? res.preview_images.map((u) => toAbsoluteUrl(String(u || ""))).filter((u) => !!u)
          : []
        const preview: DocPreview = {
          kind: kind === "pdf" ? "pdf" : "docx",
          title: fileId,
          pageImageUrls: previewImages,
          downloadUrl: toAbsoluteUrl(res.download_url),
          previewUrl: res.preview_url ? toAbsoluteUrl(String(res.preview_url)) : undefined,
        }
        docPreviewByMessageId.value = { ...docPreviewByMessageId.value, [messageId]: preview }
        maybeSetActivePreview("doc", messageId)
        continue
      }

      if (kind === "xlsx") {
        const previewImages = Array.isArray(res.preview_images)
          ? res.preview_images.map((u) => toAbsoluteUrl(String(u || ""))).filter((u) => !!u)
          : []
        const previewUrl = res.preview_url ? toAbsoluteUrl(String(res.preview_url)) : undefined

        if (previewImages.length > 0 || previewUrl) {
          const preview: SheetPreview = {
            filename: fileId,
            downloadUrl: toAbsoluteUrl(res.download_url),
            previewUrl,
            pageImageUrls: previewImages,
          }
          sheetPreviewByMessageId.value = { ...sheetPreviewByMessageId.value, [messageId]: preview }
          maybeSetActivePreview("sheet", messageId)
          continue
        }
      }

      if ((kind === "proto" || kind === "html") && res.preview_url) {
        const preview: ProtoPreview = {
          project_name: fileId,
          pages: [],
          preview_url: toAbsoluteUrl(String(res.preview_url)),
        }
        protoPreviewByMessageId.value = { ...protoPreviewByMessageId.value, [messageId]: preview }
        maybeSetActivePreview("proto", messageId)
      }
    } catch {
      // ignore preview failures
    }
  }
}

function _setReadmeBusy(projectId: number, busy: boolean) {
  readmeBusyByProjectId.value = { ...readmeBusyByProjectId.value, [projectId]: busy }
}

function _setReadmeError(projectId: number, error: string | null) {
  readmeErrorByProjectId.value = { ...readmeErrorByProjectId.value, [projectId]: error }
}

async function openProjectReadme(projectId: number) {
  const pid = Number(projectId)
  if (!Number.isFinite(pid) || pid < 0) return
  if (readmeBusyByProjectId.value[pid]) return

  _setReadmeBusy(pid, true)
  _setReadmeError(pid, null)
  try {
    const res = pid === 0 ? await getTeamWorkspaceReadme() : await getTeamProjectReadme(pid)
    if (!res?.exists) {
      readmePreviewByProjectId.value = { ...readmePreviewByProjectId.value, [pid]: null }
      activePreview.value = { kind: "readme", projectId: pid }
      showToast("未找到 README")
      return
    }
    const label =
      pid === 0 ? activeWorkspaceLabel.value : teamProjects.value.find((p) => p.id === pid)?.name ?? `项目#${pid}`
    const preview: ReadmePreview = {
      projectId: pid,
      title: res.filename || "README",
      relPath: res.rel_path ?? null,
      content: res.content ?? "",
      truncated: !!res.truncated,
      sourceLabel: label,
    }
    readmePreviewByProjectId.value = { ...readmePreviewByProjectId.value, [pid]: preview }
    activePreview.value = { kind: "readme", projectId: pid }
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    const msg = formatAxiosError(e)
    _setReadmeError(pid, msg)
    showToast(msg)
    activePreview.value = { kind: "readme", projectId: pid }
  } finally {
    _setReadmeBusy(pid, false)
  }
}

async function toggleProjectTree(projectId: number) {
  const pid = Number(projectId)
  const wasExpanded = !!projectTreeExpandedById.value[pid]
  await toggleProjectTreeCore(projectId)
  if (!wasExpanded) {
    openProjectReadme(pid)
  }
}

function extractDownloadUrlFromEvents(events: any[]): string | null {
  const items = Array.isArray(events) ? events : []
  for (let i = items.length - 1; i >= 0; i--) {
    const ev = items[i]
    if (!ev || typeof ev !== "object") continue
    if (ev.type !== "tool_result") continue
    const result = (ev as any).result
    const url = typeof result?.download_url === "string" ? result.download_url.trim() : ""
    if (url) return url
  }
  return null
}

function extractPptPreviewFromEvents(events: any[]): PptPreview | null {
  const items = Array.isArray(events) ? events : []
  let coverImageUrl = ""

  for (let i = items.length - 1; i >= 0; i--) {
    const ev = items[i]
    if (!ev || typeof ev !== "object") continue

    if (ev.type === "tool_result" && ev.tool === "doc_pptx_create" && !coverImageUrl) {
      const url = typeof (ev as any)?.result?.preview_image_url === "string" ? (ev as any).result.preview_image_url.trim() : ""
      if (url) coverImageUrl = toAbsoluteUrl(url)
      continue
    }

    if (ev.type !== "tool_call") continue
    if (ev.tool !== "doc_pptx_create") continue

    const args = (ev as any).args
    const title = typeof args?.title === "string" ? args.title.trim() : ""
    const slidesRaw: unknown[] = Array.isArray(args?.slides) ? (args.slides as unknown[]) : []
    const slides: PptSlidePreview[] = slidesRaw
      .map((slide): PptSlidePreview => {
        const s = (slide as any) ?? {}
        const st = typeof s.title === "string" ? s.title.trim() : ""
        const bulletsRaw: unknown[] = Array.isArray(s.bullets) ? (s.bullets as unknown[]) : []
        const bullets = bulletsRaw.map((b) => String(b)).filter((b) => b.trim())
        return { title: st, bullets }
      })
      .filter((s) => s.title || s.bullets.length)

    if (!title || slides.length === 0) return null
    return { title, slides, coverImageUrl: coverImageUrl || undefined }
  }

  return null
}

function extractQuotePreviewFromEvents(events: any[]): QuotePreview | null {
  const items = Array.isArray(events) ? events : []
  for (let i = items.length - 1; i >= 0; i--) {
    const ev = items[i]
    if (!ev || typeof ev !== "object") continue
    if (ev.type !== "tool_call") continue
    const tool = String((ev as any).tool || "")
    if (tool !== "doc_quote_docx_create" && tool !== "doc_quote_xlsx_create") continue

    const args = (ev as any).args ?? {}
    const seller = typeof args?.seller === "string" ? args.seller.trim() : ""
    const buyer = typeof args?.buyer === "string" ? args.buyer.trim() : ""
    const currency = typeof args?.currency === "string" ? args.currency.trim() : "CNY"
    const note = typeof args?.note === "string" ? args.note.trim() : ""

    const itemsRaw: unknown[] = Array.isArray(args?.items) ? (args.items as unknown[]) : []
    const outItems: QuoteItemPreview[] = itemsRaw
      .map((it): QuoteItemPreview => {
        const v = (it as any) ?? {}
        const name = typeof v.name === "string" ? v.name.trim() : ""
        const quantity = Number(v.quantity ?? 0)
        const unit_price = Number(v.unit_price ?? 0)
        const unit = typeof v.unit === "string" ? v.unit.trim() : undefined
        return { name, quantity: Number.isFinite(quantity) ? quantity : 0, unit_price: Number.isFinite(unit_price) ? unit_price : 0, unit }
      })
      .filter((it) => it.name)

    if (!seller || !buyer || outItems.length === 0) return null
    const total = outItems.reduce((sum, it) => sum + it.quantity * it.unit_price, 0)
    return {
      kind: tool === "doc_quote_xlsx_create" ? "xlsx" : "docx",
      seller,
      buyer,
      currency: currency || "CNY",
      items: outItems,
      note: note || undefined,
      total,
    }
  }
  return null
}

function extractProtoPreviewFromEvents(events: any[]): ProtoPreview | null {
  const items = Array.isArray(events) ? events : []
  let previewUrl = ""
  let args: any = null

  for (let i = items.length - 1; i >= 0; i--) {
    const ev = items[i]
    if (!ev || typeof ev !== "object") continue

    if (ev.type === "tool_result" && (ev as any).tool === "proto_generate") {
      const result = (ev as any).result ?? {}
      const url = typeof result?.preview_url === "string" ? result.preview_url.trim() : ""
      if (url) previewUrl = url
    }

    if (ev.type === "tool_call" && (ev as any).tool === "proto_generate") {
      args = (ev as any).args ?? {}
    }

    if (previewUrl && args) break
  }

  const project_name = typeof args?.project_name === "string" ? args.project_name.trim() : ""
  const pagesRaw: unknown[] = Array.isArray(args?.pages) ? (args.pages as unknown[]) : []
  const pages: ProtoPagePreview[] = pagesRaw
    .map((p): ProtoPagePreview => {
      const v = (p as any) ?? {}
      const title = typeof v.title === "string" ? v.title.trim() : ""
      const description = typeof v.description === "string" ? v.description.trim() : ""
      return { title, description: description || undefined }
    })
    .filter((p) => p.title)

  if (!project_name || pages.length === 0 || !previewUrl) return null
  return { project_name, pages, preview_url: toAbsoluteUrl(previewUrl) }
}

function summarizeTrace(events: any[]): string[] {
  const items = Array.isArray(events) ? events : []
  const steps: string[] = []

  for (const ev of items) {
    if (!ev || typeof ev !== "object") continue
    const type = String((ev as any).type || "")

    if (type === "tool_call") {
      const tool = String((ev as any).tool || "")
      const args = (ev as any).args ?? {}
      let hint = ""
      if (tool === "doc_pptx_create") {
        const title = typeof args?.title === "string" ? args.title.trim() : ""
        if (title) hint = `（${title}）`
      } else if (tool === "proto_generate") {
        const name = typeof args?.project_name === "string" ? args.project_name.trim() : ""
        if (name) hint = `（${name}）`
      } else if (tool === "doc_quote_docx_create" || tool === "doc_quote_xlsx_create") {
        const seller = typeof args?.seller === "string" ? args.seller.trim() : ""
        const buyer = typeof args?.buyer === "string" ? args.buyer.trim() : ""
        if (seller || buyer) hint = `（${seller || "供方"} → ${buyer || "需方"}）`
      }
      steps.push(`调用工具：${tool || "（未知）"}${hint}`)
      continue
    }

    if (type === "tool_result") {
      const tool = String((ev as any).tool || "")
      const result = (ev as any).result ?? {}
      const fileId = typeof result?.file_id === "string" ? result.file_id : ""
      const filename = typeof result?.filename === "string" ? result.filename : ""
      const download = typeof result?.download_url === "string" ? result.download_url : ""
      const suffix = filename || fileId || download
      steps.push(`工具结果：${tool || "（未知）"}${suffix ? ` → ${suffix}` : ""}`)
      continue
    }

    if (type === "opencode_fallback" || type === "nanobot_fallback" || type === "codex_fallback") {
      const requested = Array.isArray((ev as any).requested) ? (ev as any).requested.join(",") : ""
      steps.push(`已切换：使用 aistaff 内置生成（${requested || "docs"}）`)
      continue
    }

    if (type === "nanobot_start") {
      steps.push("调用引擎：NanoBot")
      continue
    }

    if (type === "codex_start") {
      steps.push("调用引擎：Codex")
      continue
    }

    if (type === "task_artifact") {
      const path = String((ev as any).path || "").trim()
      const location = String((ev as any).location || "").trim()
      steps.push(`归档任务：${path || location || "已保存"}`)
      continue
    }

    if (type === "opencode_permission") {
      const perm = String((ev as any).permission || "")
      const reply = String((ev as any).reply || "")
      steps.push(`权限：${perm || "（未知）"} → ${reply || "（未知）"}`)
      continue
    }

    if (type === "opencode_done" || type === "nanobot_done" || type === "codex_done") {
      const ms = Number((ev as any).elapsed_ms ?? 0)
      if (Number.isFinite(ms) && ms > 0) steps.push(`完成：耗时 ${ms}ms`)
      continue
    }

    if (type === "codex_warning") {
      steps.push("提示：Codex 输出了额外日志")
      continue
    }

    if (type === "assistant_message") {
      steps.push("生成回复")
      continue
    }

    if (type === "error") {
      const msg = String((ev as any).message || "").trim()
      steps.push(`错误：${msg || "（未知）"}`)
      continue
    }
  }

  const deduped: string[] = []
  for (const s of steps) {
    if (!deduped.length || deduped[deduped.length - 1] !== s) deduped.push(s)
  }
  return (deduped.length ? deduped : ["（暂无可展示的轨迹）"]).slice(0, 30)
}

type TraceStepLevel = "info" | "success" | "warn" | "error"
type StructuredTraceStep = { key: string; phase: string; title: string; detail?: string; level: TraceStepLevel }

function formatToolToggleSet(value: any): string {
  const shell = value?.shell ? "shell" : "-"
  const write = value?.write ? "write" : "-"
  const browser = value?.browser ? "browser" : "-"
  const parts = [shell, write, browser]
  if (value && Object.prototype.hasOwnProperty.call(value, "dangerous")) {
    const dangerous = value?.dangerous ? "no-sandbox" : "-"
    parts.push(dangerous)
  }
  return parts.join("/")
}

function traceToolHint(tool: string, args: any): string | undefined {
  if (tool === "doc_pptx_create") {
    const title = typeof args?.title === "string" ? args.title.trim() : ""
    return title || undefined
  }
  if (tool === "proto_generate") {
    const projectName = typeof args?.project_name === "string" ? args.project_name.trim() : ""
    return projectName || undefined
  }
  if (tool === "doc_quote_docx_create" || tool === "doc_quote_xlsx_create") {
    const seller = typeof args?.seller === "string" ? args.seller.trim() : ""
    const buyer = typeof args?.buyer === "string" ? args.buyer.trim() : ""
    if (seller || buyer) return `${seller || "供方"} → ${buyer || "需方"}`
  }
  return undefined
}

function structuredTrace(events: any[]): StructuredTraceStep[] {
  const items = Array.isArray(events) ? events : []
  const steps: StructuredTraceStep[] = []

  for (const ev of items) {
    if (!ev || typeof ev !== "object") continue
    const type = String((ev as any).type || "")

    if (type === "security_profile") {
      const preset = String((ev as any).preset || "safe")
      steps.push({
        key: `security-${steps.length}`,
        phase: "安全",
        title: `档位：${preset}`,
        detail: `请求 ${formatToolToggleSet((ev as any).requested)} · 生效 ${formatToolToggleSet((ev as any).effective)}`,
        level: "info",
      })
      continue
    }

    if (type === "tool_call") {
      const tool = String((ev as any).tool || "(unknown)")
      const hint = traceToolHint(tool, (ev as any).args)
      steps.push({
        key: `tool-call-${steps.length}`,
        phase: "调用",
        title: tool,
        detail: hint,
        level: "info",
      })
      continue
    }

    if (type === "tool_result") {
      const tool = String((ev as any).tool || "(unknown)")
      const result = (ev as any).result ?? {}
      const fileHint = String(result?.filename || result?.file_id || "").trim()
      const errorHint = String(result?.error || "").trim()
      steps.push({
        key: `tool-result-${steps.length}`,
        phase: "结果",
        title: tool,
        detail: errorHint || fileHint || undefined,
        level: errorHint ? "error" : "success",
      })
      continue
    }

    if (type === "opencode_permission") {
      const permission = String((ev as any).permission || "unknown")
      const reply = String((ev as any).reply || "unknown")
      steps.push({
        key: `permission-${steps.length}`,
        phase: "权限",
        title: `${permission} → ${reply}`,
        level: reply === "reject" ? "warn" : "info",
      })
      continue
    }

    if (type === "opencode_fallback" || type === "nanobot_fallback" || type === "codex_fallback") {
      const requested = Array.isArray((ev as any).requested) ? (ev as any).requested.join(", ") : "docs"
      steps.push({
        key: `fallback-${steps.length}`,
        phase: "路由",
        title: "切换到内置 Agent",
        detail: requested,
        level: "warn",
      })
      continue
    }

    if (type === "nanobot_start") {
      steps.push({
        key: `nanobot-start-${steps.length}`,
        phase: "路由",
        title: "切换到 NanoBot",
        level: "info",
      })
      continue
    }

    if (type === "codex_start") {
      const model = String((ev as any).model || "").trim()
      const sandbox = String((ev as any).sandbox || "").trim()
      const dangerous = (ev as any).dangerous_bypass ? "no-sandbox" : ""
      steps.push({
        key: `codex-start-${steps.length}`,
        phase: "路由",
        title: "切换到 Codex",
        detail: [model, sandbox, dangerous].filter(Boolean).join(" · ") || undefined,
        level: "info",
      })
      continue
    }

    if (type === "task_artifact") {
      const path = String((ev as any).path || "").trim()
      const location = String((ev as any).location || "").trim()
      const taskId = String((ev as any).task_id || "").trim()
      steps.push({
        key: `task-${steps.length}`,
        phase: "归档",
        title: "任务已保存",
        detail: [path || location || "", taskId ? `#${taskId}` : ""].filter(Boolean).join(" · ") || undefined,
        level: "info",
      })
      continue
    }

    if (type === "opencode_done" || type === "nanobot_done" || type === "codex_done") {
      const ms = Number((ev as any).elapsed_ms ?? 0)
      steps.push({
        key: `done-${steps.length}`,
        phase: "完成",
        title: "任务完成",
        detail: Number.isFinite(ms) && ms > 0 ? `耗时 ${ms}ms` : undefined,
        level: "success",
      })
      continue
    }

    if (type === "codex_warning") {
      steps.push({
        key: `codex-warning-${steps.length}`,
        phase: "提示",
        title: "Codex 输出了额外日志",
        detail: String((ev as any).message || "").trim() || undefined,
        level: "warn",
      })
      continue
    }

    if (type === "error") {
      steps.push({
        key: `error-${steps.length}`,
        phase: "异常",
        title: String((ev as any).message || "执行失败"),
        level: "error",
      })
      continue
    }
  }

  const deduped: StructuredTraceStep[] = []
  for (const step of steps) {
    const prev = deduped[deduped.length - 1]
    if (prev && prev.phase === step.phase && prev.title === step.title && prev.detail === step.detail) continue
    deduped.push(step)
  }
  return deduped.slice(0, 40)
}

const downloadsByMessageId = computed<Record<string, DownloadLink[]>>(() => {
  const map: Record<string, DownloadLink[]> = {}
  for (const m of messages.value) {
    if (m.role !== "assistant") continue
    const links = extractDownloadLinks(m.content)
    if (links.length) map[m.id] = links
  }
  return map
})

const pptPreviewByMessageId = ref<Record<string, PptPreview>>({})
const quotePreviewByMessageId = ref<Record<string, QuotePreview>>({})
const protoPreviewByMessageId = ref<Record<string, ProtoPreview>>({})
const sheetPreviewByMessageId = ref<Record<string, SheetPreview>>({})
const docPreviewByMessageId = ref<Record<string, DocPreview>>({})
const readmePreviewByProjectId = ref<Record<number, ReadmePreview | null>>({})
const readmeBusyByProjectId = ref<Record<number, boolean>>({})
const readmeErrorByProjectId = ref<Record<number, string | null>>({})

type MessagePreviewKind = "ppt" | "quote" | "proto" | "sheet" | "doc" | "images" | "files"
type ActivePreview =
  | { kind: MessagePreviewKind; messageId: string }
  | { kind: "readme"; projectId: number }
const activePreview = ref<ActivePreview | null>(null)

const activePpt = computed<PptPreview | null>(() => {
  if (activePreview.value?.kind !== "ppt") return null
  return pptPreviewByMessageId.value[activePreview.value.messageId] ?? null
})

const activeQuote = computed<QuotePreview | null>(() => {
  if (activePreview.value?.kind !== "quote") return null
  return quotePreviewByMessageId.value[activePreview.value.messageId] ?? null
})

const activeProto = computed<ProtoPreview | null>(() => {
  if (activePreview.value?.kind !== "proto") return null
  return protoPreviewByMessageId.value[activePreview.value.messageId] ?? null
})

const activeSheet = computed<SheetPreview | null>(() => {
  if (activePreview.value?.kind !== "sheet") return null
  return sheetPreviewByMessageId.value[activePreview.value.messageId] ?? null
})

const activeDoc = computed<DocPreview | null>(() => {
  if (activePreview.value?.kind !== "doc") return null
  return docPreviewByMessageId.value[activePreview.value.messageId] ?? null
})

const activeReadme = computed<ReadmePreview | null>(() => {
  if (activePreview.value?.kind !== "readme") return null
  return readmePreviewByProjectId.value[activePreview.value.projectId] ?? null
})

const activeReadmeBusy = computed<boolean>(() => {
  if (activePreview.value?.kind !== "readme") return false
  return !!readmeBusyByProjectId.value[activePreview.value.projectId]
})

const activeReadmeError = computed<string | null>(() => {
  if (activePreview.value?.kind !== "readme") return null
  return readmeErrorByProjectId.value[activePreview.value.projectId] ?? null
})

const activeImages = computed<UiAttachment[]>(() => {
  const ap = activePreview.value
  if (!ap || ap.kind !== "images") return []
  const msg = messages.value.find((m) => m.id === ap.messageId)
  return msg?.attachments?.filter((a) => a.kind === "image") ?? []
})

const activeFileDownloads = computed<DownloadLink[]>(() => {
  const ap = activePreview.value
  if (!ap) return []
  if (ap.kind === "readme") return []
  return downloadsByMessageId.value[ap.messageId] ?? []
})

function _fileKindFromId(fileId: string): string {
  const v = (fileId || "").toLowerCase()
  if (v.endsWith(".pptx") || v.endsWith(".ppt")) return "ppt"
  if (v.endsWith(".docx") || v.endsWith(".doc")) return "doc"
  if (v.endsWith(".pdf")) return "pdf"
  if (v.endsWith(".xlsx") || v.endsWith(".xls")) return "xls"
  if (v.endsWith(".zip")) return "zip"
  if (v.endsWith(".png") || v.endsWith(".jpg") || v.endsWith(".jpeg") || v.endsWith(".webp") || v.endsWith(".gif")) return "img"
  return "file"
}

function _fileIdFromDownload(url: string): string {
  const value = (url || "").trim()
  const m = value.match(/\/api\/files\/([A-Za-z0-9][A-Za-z0-9._-]{0,199})\?token=/)
  return m?.[1] ?? value
}

function formatMoney(value: number): string {
  const v = Number(value ?? 0)
  const n = Number.isFinite(v) ? v : 0
  return n.toFixed(2)
}

async function copyToClipboard(text: string) {
  const value = (text || "").trim()
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    showToast("已复制")
    return
  } catch {
    // fallback below
  }

  const ta = document.createElement("textarea")
  ta.value = value
  ta.setAttribute("readonly", "true")
  ta.style.position = "fixed"
  ta.style.top = "0"
  ta.style.left = "0"
  ta.style.opacity = "0"
  document.body.appendChild(ta)
  ta.focus()
  ta.select()
  try {
    document.execCommand("copy")
    showToast("已复制")
  } finally {
    document.body.removeChild(ta)
  }
}

function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark"
}

function formatApiDetail(detail: any): string | null {
  if (detail == null) return null
  if (typeof detail === "string") {
    const s = detail.trim()
    return s ? s : null
  }
  if (Array.isArray(detail)) {
    const lines = detail
      .map((e) => {
        if (!e || typeof e !== "object") return String(e)
        const msg = typeof (e as any).msg === "string" ? (e as any).msg : ""
        const loc = Array.isArray((e as any).loc) ? (e as any).loc.join(".") : ""
        if (loc && msg) return `${loc}: ${msg}`
        return msg || JSON.stringify(e)
      })
      .filter((x) => x && x.trim())
    return lines.join("\n")
  }
  try {
    return JSON.stringify(detail)
  } catch {
    return String(detail)
  }
}

function formatAxiosError(e: any): string {
  const detail = formatApiDetail(e?.response?.data?.detail)
  if (detail) return detail
  const data = e?.response?.data
  if (typeof data === "string" && data.trim()) return data.trim()
  const status = e?.response?.status
  if (Number.isFinite(status) && status > 0) return `请求失败（HTTP ${status}）`
  return e?.message || String(e)
}

function handleUnauthorized(e: any): boolean {
  if (e?.response?.status === 401) {
    authError.value = "登录已失效，请重新登录"
    logout()
    return true
  }
  return false
}

function applyAuth(res: AuthResponse) {
  authToken.value = res.access_token
  localStorage.setItem("aistaff_token", res.access_token)
  setAuthToken(res.access_token)
  me.value = { user: res.user, teams: res.teams, active_team: res.active_team }
  activeTeamId.value = res.active_team.id
  const email = normalizeEmail(res?.user?.email || "")
  if (email) {
    setLastTeamIdForEmail(email, Number(res?.active_team?.id || 0))
    markTeamOnboarded(email)
  }
}

async function loadBuiltinSkills() {
  try {
    const items = await listSkills()
    skills.value = items

    const stillExists = items.some((item) => item.id === selectedSkillId.value)
    if (!stillExists) selectedSkillId.value = items[0]?.id ?? ""

    const nextPayloadById: Record<string, unknown> = { ...skillPayloadById.value }
    for (const s of items) {
      if (!(s.id in nextPayloadById)) {
        nextPayloadById[s.id] = cloneSkillPayload(s.default_payload ?? {})
      }
    }
    skillPayloadById.value = nextPayloadById
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    skillError.value = formatAxiosError(e)
  }
}

function resetSelectedSkillPayload() {
  const skill = selectedSkill.value
  if (!skill) return
  skillPayloadById.value = {
    ...skillPayloadById.value,
    [skill.id]: cloneSkillPayload(skill.default_payload ?? {}),
  }
  skillError.value = null
  skillDownloadById.value = { ...skillDownloadById.value, [skill.id]: null }
}

function historyMessageContent(m: any): string {
  const role = String(m?.role || "")
  let out = String(m?.content || "")
  if (role === "assistant") {
    const urlFromEvents = extractDownloadUrlFromEvents(Array.isArray(m?.events) ? m.events : [])
    if (urlFromEvents && !out.includes("/api/files/")) out = `${out}\n\n下载：${urlFromEvents}`.trim()
  }
  return out
}

function historyMessageDownloads(m: any): DownloadLink[] {
  return extractDownloadLinks(historyMessageContent(m))
}

function historyEventsOf(m: any): any[] {
  const ev = (m as any)?.events
  return Array.isArray(ev) ? ev : []
}

async function openHistorySession(sessionId: string) {
  selectedHistorySessionId.value = sessionId
  showHistoryModal.value = true
  historyDetailBusy.value = true
  historyDetailError.value = null
  historyDetail.value = null
  try {
    const res = await getHistorySession(sessionId)
    historyDetail.value = {
      session: res.session,
      messages: (res.messages ?? []).map((m) => ({
        ...m,
        attachments: (m.attachments ?? []).map((a) => ({ ...a, download_url: toAbsoluteUrl(a.download_url) })),
      })),
    }
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    historyDetailError.value = formatAxiosError(e)
  } finally {
    historyDetailBusy.value = false
  }
}

function loadHistoryIntoChat() {
  const detail = historyDetail.value
  if (!detail?.session) return
  if (sending.value) return

  const ok = messages.value.length ? confirm("加载历史会覆盖当前对话并继续该会话，是否继续？") : true
  if (!ok) return

  const targetProjectId = typeof detail.session.project_id === "number" && detail.session.project_id > 0 ? detail.session.project_id : 0
  activeProjectId.value = targetProjectId
  previousProjectId.value = targetProjectId

  const nextRole = detail.session.role === "engineer" ? "engineer" : "general"
  role.value = nextRole
  const nextProvider =
    detail.session.provider === "openai" ||
    detail.session.provider === "opencode" ||
    detail.session.provider === "nanobot" ||
    detail.session.provider === "codex" ||
    detail.session.provider === "mock"
      ? detail.session.provider
      : provider.value
  provider.value = nextProvider

  reset()
  sessionId.value = detail.session.session_id

  const nextEvents: Record<string, any[]> = {}
  const nextPpt: Record<string, PptPreview> = {}
  const nextQuote: Record<string, QuotePreview> = {}
  const nextProto: Record<string, ProtoPreview> = {}
  const nextSheet: Record<string, SheetPreview> = {}
  const nextDoc: Record<string, DocPreview> = {}

  const nextMessages: UiMessage[] = (detail.messages ?? []).map((m) => {
    const id = `h${m.id}`
    const ts = new Date(m.created_at).getTime()
    const safeTs = Number.isFinite(ts) ? ts : Date.now()
    const attachments: UiAttachment[] = (m.attachments ?? []).map((a) => ({
      kind: a.kind === "image" ? "image" : "file",
      url: toAbsoluteUrl(a.download_url),
      filename: a.filename ?? undefined,
      file_id: a.file_id,
      content_type: a.content_type ?? undefined,
    }))

    if (m.role === "assistant") {
      const evs = Array.isArray((m as any).events) ? ((m as any).events as any[]) : []
      if (evs.length) nextEvents[id] = evs

      const ppt = extractPptPreviewFromEvents(evs)
      if (ppt) nextPpt[id] = ppt
      const quote = extractQuotePreviewFromEvents(evs)
      if (quote) nextQuote[id] = quote
      const proto = extractProtoPreviewFromEvents(evs)
      if (proto) nextProto[id] = proto
    }

    return {
      id,
      role: m.role === "assistant" ? "assistant" : "user",
      content: historyMessageContent(m),
      ts: safeTs,
      attachments: attachments.length ? attachments : undefined,
    }
  })

  messages.value = nextMessages
  eventsByMessageId.value = nextEvents
  pptPreviewByMessageId.value = nextPpt
  quotePreviewByMessageId.value = nextQuote
  protoPreviewByMessageId.value = nextProto
  sheetPreviewByMessageId.value = nextSheet
  docPreviewByMessageId.value = nextDoc

  const last = [...nextMessages].reverse().find((m) => m.role === "assistant") ?? null
  if (last) {
    const id = last.id
    const proto = nextProto[id]
    const ppt = nextPpt[id]
    const quote = nextQuote[id]
    if (proto) activePreview.value = { kind: "proto", messageId: id }
    else if (ppt) activePreview.value = { kind: "ppt", messageId: id }
    else if (quote) activePreview.value = { kind: "quote", messageId: id }
    else if (extractDownloadLinks(last.content).length) activePreview.value = { kind: "files", messageId: id }
  }

  closeHistoryModal()
}

async function removeHistorySession(sessionId: string) {
  const ok = confirm(`确定删除会话「${sessionId}」吗？此操作不可恢复。`)
  if (!ok) return
  historySessionsBusy.value = true
  historyError.value = null
  try {
    await deleteHistorySession(sessionId)
    if (historyDetail.value?.session?.session_id === sessionId) closeHistoryModal()
    if (selectedHistorySessionId.value === sessionId) selectedHistorySessionId.value = null
    await refreshHistorySessions()
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    historyError.value = formatAxiosError(e)
  } finally {
    historySessionsBusy.value = false
  }
}

function onSwitchProject() {
  const next = activeProjectId.value
  const prev = previousProjectId.value
  if (next === prev) return

  if (sending.value) {
    activeProjectId.value = prev
    return
  }

  const nextName =
    next > 0
      ? teamProjects.value.find((p) => p.id === next)?.name ?? String(next)
      : teamWorkspacePath.value
        ? "团队工作区"
        : "默认工作区"
  if (messages.value.length) {
    const ok = confirm(`切换工作区到「${nextName}」会开始新会话并清空当前对话，是否继续？`)
    if (!ok) {
      activeProjectId.value = prev
      return
    }
  }
  previousProjectId.value = next
  reset()
  void refreshHistory()
}

function switchWorkspaceProject(projectId: number) {
  if (activeProjectId.value === projectId) return
  activeProjectId.value = projectId
  onSwitchProject()
}

async function saveTeamWorkspace() {
  if (!canEditTeamProjects.value) return
  if (sending.value) return

  teamSettingsError.value = null
  const next = teamWorkspaceDraft.value.trim()
  const affectsCurrentChat = activeProjectId.value === 0
  if (affectsCurrentChat && messages.value.length) {
    const ok = confirm("修改团队工作区会开始新会话并清空当前对话，是否继续？")
    if (!ok) return
  }

  teamSettingsBusy.value = true
  try {
    const res = await updateTeamSettings({ workspace_path: next || null })
    teamSettings.value = res
    teamWorkspaceDraft.value = (res.workspace_path || "").trim()
    if (affectsCurrentChat) {
      previousProjectId.value = 0
      reset()
    }
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamSettingsError.value = formatAxiosError(e)
  } finally {
    teamSettingsBusy.value = false
  }
}

async function clearTeamWorkspace() {
  if (!canEditTeamProjects.value) return
  if (!teamWorkspacePath.value) return
  const ok = confirm("确定清空团队工作区？清空后将回退到服务端默认工作区（AISTAFF_WORKSPACE）。")
  if (!ok) return
  teamWorkspaceDraft.value = ""
  await saveTeamWorkspace()
}

function openProjectManager() {
  showProjectModal.value = true
  void refreshTeamFeishuWebhooks()
  if (selectedTeamProjectId.value !== null) return
  if (teamProjects.value.length > 0) selectTeamProject(teamProjects.value[0]!)
  else if (canEditTeamProjects.value) newTeamProject()
}

function openProjectManagerForProject(p: TeamProject) {
  openProjectManager()
  selectTeamProject(p)
}

function openProjectManagerForNewProject() {
  openProjectManager()
  if (canEditTeamProjects.value) newTeamProject()
}

function selectTeamProject(p: TeamProject) {
  selectedTeamProjectId.value = p.id
  teamProjectForm.value = {
    name: p.name ?? "",
    slug: p.slug ?? "",
    path: p.path ?? "",
    enabled: !!p.enabled,
  }
}

function newTeamProject() {
  selectedTeamProjectId.value = "new"
  teamProjectForm.value = {
    name: "新项目",
    slug: "",
    path: "",
    enabled: true,
  }
}

async function quickImportTeamProjects() {
  if (!canEditTeamProjects.value) return
  if (teamProjectsBusy.value) return

  teamProjectsBusy.value = true
  teamProjectsError.value = null
  try {
    const discovered = await discoverTeamProjects({ max_entries: 240 })
    const paths = discovered
      .filter((item) => !item.already_added)
      .map((item) => item.path)
      .slice(0, 120)

    if (!paths.length) {
      showToast("未发现可导入的新项目")
      return
    }

    const ok = confirm(`发现 ${paths.length} 个候选项目，是否一键导入？`)
    if (!ok) return

    const result = await importTeamProjects({ paths, enabled: true })
    await refreshTeamProjects()

    if (result.created.length > 0) {
      const first = teamProjects.value.find((item) => item.id === result.created[0]?.id)
      if (first) selectTeamProject(first)
    }

    if (result.created.length > 0 && result.skipped.length > 0) {
      showToast(`已导入 ${result.created.length} 个，跳过 ${result.skipped.length} 个`)
    } else if (result.created.length > 0) {
      showToast(`已导入 ${result.created.length} 个项目`)
    } else {
      showToast("没有导入新的项目")
    }
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamProjectsError.value = formatAxiosError(e)
  } finally {
    teamProjectsBusy.value = false
  }
}

function selectTeamRequirement(item: TeamRequirement) {
  selectedTeamRequirementId.value = item.id
  teamRequirementForm.value = {
    project_id: item.project_id ?? 0,
    source_team: item.source_team ?? "",
    title: item.title ?? "",
    description: item.description ?? "",
    status: item.status ?? "incoming",
    priority: item.priority ?? "medium",
    delivery_target_team_id: 0,
  }
}

function newTeamRequirement() {
  selectedTeamRequirementId.value = "new"
  teamRequirementForm.value = {
    project_id: activeProjectId.value > 0 ? activeProjectId.value : 0,
    source_team: "",
    title: "",
    description: "",
    status: "incoming",
    priority: "medium",
    delivery_target_team_id: 0,
  }
}

async function quickSetRequirementStatus(item: TeamRequirement, status: TeamRequirement["status"]) {
  if (!canEditTeamRequirements.value) return
  if (item.status === status) return
  teamRequirementsBusy.value = true
  teamRequirementsError.value = null
  try {
    await updateTeamRequirement(item.id, { status })
    await refreshTeamRequirements()
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamRequirementsError.value = formatAxiosError(e)
  } finally {
    teamRequirementsBusy.value = false
  }
}

async function saveTeamRequirement() {
  if (!canEditTeamRequirements.value) return
  teamRequirementsError.value = null

  const form = {
    project_id: teamRequirementForm.value.project_id > 0 ? teamRequirementForm.value.project_id : null,
    source_team: teamRequirementForm.value.source_team.trim(),
    title: teamRequirementForm.value.title.trim(),
    description: teamRequirementForm.value.description.trim(),
    status: teamRequirementForm.value.status,
    priority: teamRequirementForm.value.priority,
  }

  if (!form.title) {
    teamRequirementsError.value = "请填写“需求标题”。"
    return
  }

  teamRequirementsBusy.value = true
  try {
    if (selectedTeamRequirementId.value === "new") {
      const created = await createTeamRequirement(form)
      await refreshTeamRequirements()
      const found = teamRequirements.value.find((item) => item.id === created.id)
      if (found) selectTeamRequirement(found)
    } else if (typeof selectedTeamRequirementId.value === "number") {
      const updated = await updateTeamRequirement(selectedTeamRequirementId.value, form)
      await refreshTeamRequirements()
      const found = teamRequirements.value.find((item) => item.id === updated.id)
      if (found) selectTeamRequirement(found)
    }
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamRequirementsError.value = formatAxiosError(e)
  } finally {
    teamRequirementsBusy.value = false
  }
}

async function removeTeamRequirement() {
  if (!canEditTeamRequirements.value) return
  if (typeof selectedTeamRequirementId.value !== "number") return
  const id = selectedTeamRequirementId.value
  const item = teamRequirements.value.find((x) => x.id === id)
  const ok = confirm(`确定删除需求「${item?.title ?? id}」吗？`)
  if (!ok) return

  teamRequirementsBusy.value = true
  teamRequirementsError.value = null
  try {
    await deleteTeamRequirement(id)
    selectedTeamRequirementId.value = null
    await refreshTeamRequirements()
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamRequirementsError.value = formatAxiosError(e)
  } finally {
    teamRequirementsBusy.value = false
  }
}

function selectTeamFeishuWebhook(item: TeamFeishuWebhook) {
  selectedTeamFeishuId.value = item.id
  teamFeishuForm.value = {
    name: item.name ?? "",
    webhook_url: item.webhook_url ?? "",
    verification_token: item.verification_token ?? "",
    enabled: !!item.enabled,
  }
}

function newTeamFeishuWebhook() {
  selectedTeamFeishuId.value = "new"
  teamFeishuForm.value = {
    name: "飞书机器人",
    webhook_url: "",
    verification_token: "",
    enabled: true,
  }
}

async function refreshTeamFeishuWebhooks() {
  teamFeishuBusy.value = true
  teamFeishuError.value = null
  try {
    const items = await listTeamFeishuWebhooks()
    teamFeishuWebhooks.value = items

    const current = selectedTeamFeishuId.value
    if (current === "new") return

    const preferredId = typeof current === "number" ? current : null
    const found = preferredId ? items.find((item) => item.id === preferredId) : null
    if (found) {
      selectTeamFeishuWebhook(found)
      return
    }

    if (items.length > 0) {
      const first = items[0]
      if (first) selectTeamFeishuWebhook(first)
    } else if (canEditTeamFeishu.value) {
      newTeamFeishuWebhook()
    } else {
      selectedTeamFeishuId.value = null
    }
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamFeishuError.value = formatAxiosError(e)
  } finally {
    teamFeishuBusy.value = false
  }
}

async function importTeamFeishuPreset() {
  if (!canEditTeamFeishu.value) return

  teamFeishuBusy.value = true
  teamFeishuError.value = null
  try {
    const ensured = await ensureTeamFeishuPreset()
    await refreshTeamFeishuWebhooks()
    const found = teamFeishuWebhooks.value.find((item) => item.id === ensured.id)
    if (found) selectTeamFeishuWebhook(found)
    feishuManageMode.value = "single"
    showToast("飞书预配置已导入")
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamFeishuError.value = formatAxiosError(e)
  } finally {
    teamFeishuBusy.value = false
  }
}

async function toggleTeamFeishuEnabled(item: TeamFeishuWebhook, enabled: boolean) {
  if (!canEditTeamFeishu.value) return
  if (!!item.enabled === !!enabled) return

  teamFeishuBusy.value = true
  teamFeishuError.value = null
  try {
    await updateTeamFeishuWebhook(item.id, { enabled })
    await refreshTeamFeishuWebhooks()
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamFeishuError.value = formatAxiosError(e)
  } finally {
    teamFeishuBusy.value = false
  }
}

async function setAllTeamFeishuEnabled(enabled: boolean) {
  if (!canEditTeamFeishu.value) return

  const targets = teamFeishuWebhooks.value.filter((item) => !!item.enabled !== !!enabled)
  if (!targets.length) return

  teamFeishuBusy.value = true
  teamFeishuError.value = null
  try {
    for (const item of targets) {
      await updateTeamFeishuWebhook(item.id, { enabled })
    }
    await refreshTeamFeishuWebhooks()
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamFeishuError.value = formatAxiosError(e)
  } finally {
    teamFeishuBusy.value = false
  }
}

async function saveTeamFeishuWebhook() {
  if (!canEditTeamFeishu.value) return
  teamFeishuError.value = null

  const form = {
    name: teamFeishuForm.value.name.trim(),
    webhook_url: teamFeishuForm.value.webhook_url.trim(),
    verification_token: teamFeishuForm.value.verification_token.trim(),
    enabled: !!teamFeishuForm.value.enabled,
  }
  if (!form.name || !form.webhook_url) {
    teamFeishuError.value = "请填写“名称”和“Webhook URL”。"
    return
  }

  teamFeishuBusy.value = true
  try {
    if (selectedTeamFeishuId.value === "new") {
      const created = await createTeamFeishuWebhook({
        name: form.name,
        webhook_url: form.webhook_url,
        verification_token: form.verification_token || null,
        enabled: form.enabled,
      })
      await refreshTeamFeishuWebhooks()
      const found = teamFeishuWebhooks.value.find((item) => item.id === created.id)
      if (found) selectTeamFeishuWebhook(found)
    } else if (typeof selectedTeamFeishuId.value === "number") {
      const updated = await updateTeamFeishuWebhook(selectedTeamFeishuId.value, {
        name: form.name,
        webhook_url: form.webhook_url,
        verification_token: form.verification_token || null,
        enabled: form.enabled,
      })
      await refreshTeamFeishuWebhooks()
      const found = teamFeishuWebhooks.value.find((item) => item.id === updated.id)
      if (found) selectTeamFeishuWebhook(found)
    }
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamFeishuError.value = formatAxiosError(e)
  } finally {
    teamFeishuBusy.value = false
  }
}

async function removeTeamFeishuWebhook() {
  if (!canEditTeamFeishu.value) return
  if (typeof selectedTeamFeishuId.value !== "number") return
  const id = selectedTeamFeishuId.value
  const item = teamFeishuWebhooks.value.find((x) => x.id === id)
  const ok = confirm(`确定删除飞书 Webhook「${item?.name ?? id}」吗？`)
  if (!ok) return

  teamFeishuBusy.value = true
  teamFeishuError.value = null
  try {
    await deleteTeamFeishuWebhook(id)
    selectedTeamFeishuId.value = null
    await refreshTeamFeishuWebhooks()
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamFeishuError.value = formatAxiosError(e)
  } finally {
    teamFeishuBusy.value = false
  }
}

async function saveTeamProject() {
  if (!canEditTeamProjects.value) return
  teamProjectsError.value = null

  const form = {
    name: teamProjectForm.value.name.trim(),
    slug: teamProjectForm.value.slug.trim() || undefined,
    path: teamProjectForm.value.path.trim(),
    enabled: !!teamProjectForm.value.enabled,
  }
  if (!form.name || !form.path) {
    teamProjectsError.value = "请填写“名称”和“路径”。"
    return
  }

  teamProjectsBusy.value = true
  try {
    if (selectedTeamProjectId.value === "new") {
      const created = await createTeamProject(form)
      await refreshTeamProjects()
      const found = teamProjects.value.find((p) => p.id === created.id)
      if (found) selectTeamProject(found)
    } else if (typeof selectedTeamProjectId.value === "number") {
      const updated = await updateTeamProject(selectedTeamProjectId.value, form)
      await refreshTeamProjects()
      const found = teamProjects.value.find((p) => p.id === updated.id)
      if (found) selectTeamProject(found)
    }
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamProjectsError.value = formatAxiosError(e)
  } finally {
    teamProjectsBusy.value = false
  }
}

async function removeTeamProject() {
  if (!canEditTeamProjects.value) return
  if (typeof selectedTeamProjectId.value !== "number") return
  const id = selectedTeamProjectId.value
  const p = teamProjects.value.find((x) => x.id === id)
  const ok = confirm(`确定删除项目「${p?.name ?? id}」吗？`)
  if (!ok) return

  teamProjectsBusy.value = true
  teamProjectsError.value = null
  try {
    await deleteTeamProject(id)
    if (activeProjectId.value === id) {
      activeProjectId.value = 0
      previousProjectId.value = 0
      reset()
    }
    selectedTeamProjectId.value = null
    await refreshTeamProjects()
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamProjectsError.value = formatAxiosError(e)
  } finally {
    teamProjectsBusy.value = false
  }
}

function selectTeamSkill(s: TeamSkill) {
  selectedTeamSkillId.value = s.id
  teamSkillForm.value = {
    name: s.name ?? "",
    description: s.description ?? "",
    content: s.content ?? "",
    enabled: !!s.enabled,
  }
}

function newTeamSkill() {
  selectedTeamSkillId.value = "new"
  teamSkillForm.value = {
    name: "团队规范",
    description: "团队统一输出/流程/风格要求",
    content: "- 输出统一中文\n- 先澄清再执行\n- 结果给到可复制的步骤/命令/文件路径",
    enabled: true,
  }
}

async function saveTeamSkill() {
  if (!canEditTeamSkills.value) return
  teamSkillsError.value = null
  const form = {
    name: teamSkillForm.value.name.trim(),
    description: teamSkillForm.value.description.trim(),
    content: teamSkillForm.value.content.trim(),
    enabled: !!teamSkillForm.value.enabled,
  }
  if (!form.name || !form.content) {
    teamSkillsError.value = "请填写“技能名称”和“内容”。"
    return
  }

  teamSkillsBusy.value = true
  try {
    if (selectedTeamSkillId.value === "new") {
      const created = await createTeamSkill(form)
      await refreshTeamSkills()
      const found = teamSkills.value.find((s) => s.id === created.id)
      if (found) selectTeamSkill(found)
    } else if (typeof selectedTeamSkillId.value === "number") {
      const updated = await updateTeamSkill(selectedTeamSkillId.value, form)
      await refreshTeamSkills()
      const found = teamSkills.value.find((s) => s.id === updated.id)
      if (found) selectTeamSkill(found)
    }
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamSkillsError.value = formatAxiosError(e)
  } finally {
    teamSkillsBusy.value = false
  }
}

async function aiGenerateTeamSkill() {
  if (!canEditTeamSkills.value) return

  const idea = prompt(
    "描述你要创建的团队技能（会生成名称/说明/内容草稿，不会自动保存）",
    teamSkillForm.value.description.trim() || teamSkillForm.value.name.trim() || "",
  )
  if (!idea || !idea.trim()) return

  if (teamSkillForm.value.content.trim()) {
    const ok = confirm("AI 生成会覆盖当前“内容”，是否继续？")
    if (!ok) return
  }

  teamSkillsBusy.value = true
  teamSkillsError.value = null
  try {
    const res = await aiDraftTeamSkill({
      idea: idea.trim(),
      name: teamSkillForm.value.name.trim() || undefined,
      description: teamSkillForm.value.description.trim() || undefined,
      draft: teamSkillForm.value.content.trim() || undefined,
    })
    teamSkillForm.value.name = res.name
    teamSkillForm.value.description = res.description
    teamSkillForm.value.content = res.content
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamSkillsError.value = formatAxiosError(e)
  } finally {
    teamSkillsBusy.value = false
  }
}

async function removeTeamSkill() {
  if (!canEditTeamSkills.value) return
  if (typeof selectedTeamSkillId.value !== "number") return
  const id = selectedTeamSkillId.value
  const s = teamSkills.value.find((x) => x.id === id)
  const ok = confirm(`确定删除团队技能「${s?.name ?? id}」吗？`)
  if (!ok) return

  teamSkillsBusy.value = true
  teamSkillsError.value = null
  try {
    await deleteTeamSkill(id)
    selectedTeamSkillId.value = null
    await refreshTeamSkills()
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamSkillsError.value = formatAxiosError(e)
  } finally {
    teamSkillsBusy.value = false
  }
}

async function exportTeamDbMd() {
  teamDbExportBusy.value = true
  teamDbExportError.value = null
  try {
    const res = await exportTeamDbMarkdown({ project_id: activeProjectId.value })
    teamDbExport.value = res
    showToast(`已导出：${res.filename}`)
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    teamDbExportError.value = formatAxiosError(e)
  } finally {
    teamDbExportBusy.value = false
  }
}

async function loadAfterAuth() {
  await Promise.all([
    loadBuiltinSkills(),
    refreshTeamSkills(),
    refreshTeamSettings(),
    refreshTeamProjects(),
    refreshTeamRequirements(),
    refreshTeamFeishuWebhooks(),
    refreshHistory(),
  ])
}

function logout() {
  closeHistoryModal()
  authToken.value = null
  localStorage.removeItem("aistaff_token")
  setAuthToken(null)
  me.value = null
  activeTeamId.value = null
  skills.value = []
  selectedSkillId.value = ""
  skillPayloadById.value = {}
  skillDownloadById.value = {}
  skillError.value = null
  teamSkills.value = []
  teamSkillsError.value = null
  selectedTeamSkillId.value = null
  teamProjects.value = []
  teamProjectsError.value = null
  projectSearch.value = ""
  teamSettings.value = null
  teamSettingsError.value = null
  teamWorkspaceDraft.value = ""
  teamFeishuWebhooks.value = []
  teamFeishuError.value = null
  selectedTeamFeishuId.value = null
  teamFeishuForm.value = { name: "", webhook_url: "", verification_token: "", enabled: true }
  teamRequirements.value = []
  teamRequirementsError.value = null
  selectedTeamRequirementId.value = null
  requirementSearch.value = ""
  requirementStatusFilter.value = ""
  requirementPriorityFilter.value = ""
  teamRequirementForm.value = {
    project_id: 0,
    source_team: "",
    title: "",
    description: "",
    status: "incoming",
    priority: "medium",
    delivery_target_team_id: 0,
  }
  historySessions.value = []
  historyFiles.value = []
  historyError.value = null
  selectedHistorySessionId.value = null
  activeProjectId.value = 0
  previousProjectId.value = 0
  selectedTeamProjectId.value = null
  showProjectModal.value = false
	  reset()
	}

function cancelLoginTeamPick() {
  pendingLoginTeamPick.value = null
  pendingLoginTeamId.value = 0
  authError.value = null
}

async function confirmLoginTeamPick() {
  authError.value = null
  const pending = pendingLoginTeamPick.value
  if (!pending) return

  const selected = Number(pendingLoginTeamId.value || 0)
  const teams = Array.isArray(pending.teams) ? pending.teams : []
  if (!selected || !teams.some((t) => Number((t as any)?.id || 0) === selected)) {
    authError.value = "请选择团队"
    return
  }

  authBusy.value = true
  const prevToken = authToken.value
  try {
    let res = pending
    if (selected !== Number((pending as any)?.active_team?.id || 0)) {
      setAuthToken(pending.access_token)
      res = await switchTeam(selected)
    }
    applyAuth(res)
    pendingLoginTeamPick.value = null
    pendingLoginTeamId.value = 0
    await loadAfterAuth()
  } catch (e: any) {
    authError.value = formatAxiosError(e)
    setAuthToken(prevToken)
  } finally {
    authBusy.value = false
  }
		}

		async function submitRegister() {
		  authError.value = null
		  const team_id = Math.floor(Number(registerTeamId.value || 0))
		  const invite_token = String(registerInviteToken.value || "").trim()
		  const name = String(registerName.value || "").trim()
		  const email = String(registerEmail.value || "").trim()
		  const password = String(registerPassword.value || "")
		  const password2 = String(registerPassword2.value || "")

		  if (!team_id) {
		    authError.value = "请选择团队"
		    return
		  }
		  if (!invite_token) {
		    authError.value = "请填写邀请码"
		    return
		  }
		  if (!name) {
		    authError.value = "请填写你的名字"
		    return
		  }
		  if (!email) {
		    authError.value = "请填写邮箱"
		    return
		  }
		  if ((password || "").length < 6) {
		    authError.value = "密码至少 6 位"
		    return
		  }
		  if (password !== password2) {
		    authError.value = "两次密码不一致"
		    return
		  }

		  authBusy.value = true
		  try {
		    const res = await authRegister({ invite_token, team_id, name, email, password })
		    applyAuth(res)
		    authMode.value = "login"
		    registerInviteToken.value = ""
		    registerName.value = ""
		    registerEmail.value = ""
		    registerPassword.value = ""
		    registerPassword2.value = ""
		    registerTeamId.value = 0
		    await loadAfterAuth()
		  } catch (e: any) {
		    authError.value = formatAxiosError(e)
		  } finally {
		    authBusy.value = false
		  }
		}

		async function submitLogin() {
		  authError.value = null
		  const email = normalizeEmail(loginEmail.value)
		  if (!email) {
	    authError.value = "请填写邮箱"
	    return
	  }
	  if (!loginPassword.value) {
    authError.value = "请填写密码"
    return
  }

	  authBusy.value = true
	  try {
	    const preferredTeamId = getLastTeamIdForEmail(email)
	    let res: AuthResponse
	    try {
	      res = await authLogin({ email, password: loginPassword.value, team_id: preferredTeamId ?? undefined })
	    } catch (e: any) {
	      if (preferredTeamId && e?.response?.status === 403) {
	        clearLastTeamIdForEmail(email)
	        res = await authLogin({ email, password: loginPassword.value })
	      } else {
	        throw e
	      }
	    }

	    const userEmail = normalizeEmail(res?.user?.email || email)
	    const teams = Array.isArray(res?.teams) ? res.teams : []
	    if (teams.length > 1 && !isTeamOnboarded(userEmail)) {
	      pendingLoginTeamPick.value = res
	      pendingLoginTeamId.value = Number(res?.active_team?.id || 0)
	      return
	    }

	    applyAuth(res)
	    await loadAfterAuth()
	  } catch (e: any) {
	    authError.value = formatAxiosError(e)
	  } finally {
	    authBusy.value = false
	  }
}

async function submitSetup() {
  authError.value = null
  const team_name = setupTeamName.value.trim()
  const name = setupName.value.trim()
  const email = setupEmail.value.trim()
  const password = setupPassword.value

  if (!team_name) {
    authError.value = "请填写团队名称"
    return
  }
  if (!name) {
    authError.value = "请填写你的名字"
    return
  }
  if (!email) {
    authError.value = "请填写邮箱"
    return
  }
  if ((password || "").length < 6) {
    authError.value = "密码至少 6 位"
    return
  }

  authBusy.value = true
  try {
    const res = await authSetup({
      team_name,
      name,
      email,
      password,
    })
    applyAuth(res)
    setupRequired.value = false
    await loadAfterAuth()
  } catch (e: any) {
    authError.value = formatAxiosError(e)
  } finally {
    authBusy.value = false
  }
}

async function onSwitchTeam() {
  if (!me.value || !activeTeamId.value) return
  const beforeTeamId = me.value.active_team.id
  if (activeTeamId.value === beforeTeamId) return
  try {
    const res = await switchTeam(activeTeamId.value)
    applyAuth(res)
    closeHistoryModal()
    selectedHistorySessionId.value = null
    reset()
    await loadAfterAuth()
  } catch (e: any) {
    authError.value = formatAxiosError(e)
    activeTeamId.value = beforeTeamId
  }
}

function generateLocalId() {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID()
    }
    if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
      const bytes = new Uint8Array(16)
      crypto.getRandomValues(bytes)
      const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")
      return `id_${hex}`
    }
  } catch {
    // ignore and fallback
  }
  return `id_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}

function push(roleName: UiMessage["role"], content: string, attachments?: UiAttachment[]) {
  const id = generateLocalId()
  const msg: UiMessage = { id, role: roleName, content, ts: Date.now() }
  if (attachments && attachments.length) msg.attachments = attachments
  messages.value.push(msg)
  return id
}

	function pickImages() {
	  uploadError.value = null
	  imagePickerRef.value?.click()
	}

	function pickFiles() {
	  uploadError.value = null
	  filePickerRef.value?.click()
	}

	function removePendingImage(fileId: string) {
	  pendingImages.value = pendingImages.value.filter((p) => p.file_id !== fileId)
	}

	function removePendingFile(fileId: string) {
	  pendingFiles.value = pendingFiles.value.filter((p) => p.file_id !== fileId)
	}

	async function onPickImages(e: Event) {
	  const el = e.target as HTMLInputElement | null
	  const files = Array.from(el?.files ?? [])
	  if (el) el.value = ""
	  await uploadImageFiles(files)
	}

	async function onPickFiles(e: Event) {
	  const el = e.target as HTMLInputElement | null
	  const files = Array.from(el?.files ?? [])
	  if (el) el.value = ""
	  if (!files.length) return
	  const images = files.filter(isLikelyImage)
	  const others = files.filter((f) => !isLikelyImage(f))
	  if (images.length) await uploadImageFiles(images)
	  if (others.length) await uploadAttachmentFiles(others)
	}

	const _IMG_EXT_RE = /\.(png|jpe?g|webp|gif)$/i
	function isLikelyImage(f: File): boolean {
	  const t = String(f.type || "").toLowerCase()
	  if (t.startsWith("image/")) return true
	  return _IMG_EXT_RE.test(String(f.name || ""))
	}

	async function uploadImageFiles(files: File[]) {
	  if (!files.length) return

	  uploadError.value = null
	  const remaining = Math.max(0, 4 - pendingImages.value.length)
	  const toUpload = files.slice(0, remaining)
	  if (toUpload.length < files.length) uploadError.value = "最多同时携带 4 张图片（已自动截断）。"

		  uploadingImages.value = true
		  try {
		    for (const f of toUpload) {
		      try {
		        let res: any
		        if (String(f.type || "").toLowerCase().startsWith("image/")) {
		          try {
		            res = await uploadImage(f, { project_id: activeProjectId.value > 0 ? activeProjectId.value : undefined })
		          } catch {
		            res = await uploadFile(f, { project_id: activeProjectId.value > 0 ? activeProjectId.value : undefined })
		          }
		        } else {
		          res = await uploadFile(f, { project_id: activeProjectId.value > 0 ? activeProjectId.value : undefined })
		        }
		        pendingImages.value = [
		          ...pendingImages.value,
	          {
	            file_id: res.file_id,
	            url: toAbsoluteUrl(res.download_url),
	            filename: res.filename,
	            content_type: res.content_type,
	          },
	        ]
	      } catch (err: any) {
	        if (handleUnauthorized(err)) return
	        uploadError.value = formatAxiosError(err)
		      }
		    }
		    void refreshHistoryFiles()
		  } finally {
		    uploadingImages.value = false
		  }
		}

	async function uploadAttachmentFiles(files: File[]) {
	  if (!files.length) return

	  uploadError.value = null
	  const maxFiles = 8
	  const remaining = Math.max(0, maxFiles - pendingFiles.value.length)
	  const toUpload = files.slice(0, remaining)
	  if (toUpload.length < files.length) uploadError.value = `最多同时携带 ${maxFiles} 个文件（已自动截断）。`

		  uploadingFiles.value = true
		  try {
		    for (const f of toUpload) {
		      try {
		        const res = await uploadFile(f, { project_id: activeProjectId.value > 0 ? activeProjectId.value : undefined })
		        pendingFiles.value = [
		          ...pendingFiles.value,
		          {
	            file_id: res.file_id,
	            url: toAbsoluteUrl(res.download_url),
	            filename: res.filename,
	            content_type: res.content_type,
	            size_bytes: res.size_bytes,
	          },
	        ]
	      } catch (err: any) {
	        if (handleUnauthorized(err)) return
	        uploadError.value = formatAxiosError(err)
		      }
		    }
		    void refreshHistoryFiles()
		  } finally {
		    uploadingFiles.value = false
		  }
		}

	async function onComposerPaste(e: ClipboardEvent) {
	  const items = Array.from(e.clipboardData?.items ?? [])
	  const files: File[] = []
	  for (const it of items) {
	    if (!it.type || !it.type.startsWith("image/")) continue
	    const f = it.getAsFile()
	    if (f) files.push(f)
	  }
	  if (!files.length) return
	  await uploadImageFiles(files)
	}

	async function onComposerDrop(e: DragEvent) {
	  const files = Array.from(e.dataTransfer?.files ?? [])
	  if (!files.length) return
	  const images = files.filter(isLikelyImage)
	  const others = files.filter((f) => !isLikelyImage(f))
	  if (images.length) await uploadImageFiles(images)
	  if (others.length) await uploadAttachmentFiles(others)
	}

function onComposerKeydown(e: KeyboardEvent) {
  if (e.key !== "Enter") return
  if ((e as any).isComposing) return
  if (e.shiftKey) return
  e.preventDefault()
  void send()
}

async function send() {
  if (sending.value) return
	  const imgs = pendingImages.value
	  const files = pendingFiles.value
	  let text = input.value.trim()
	  if (!text && imgs.length === 0 && files.length === 0) return
	  if (!text && imgs.length && files.length === 0) text = "请看图"
	  if (!text && files.length && imgs.length === 0) text = "请看文件"
	  if (!text && imgs.length && files.length) text = "请看附件"
	  input.value = ""
    isNearBottom.value = true
	  const userMsgId = push(
	    "user",
	    text,
	    [
	      ...imgs.map((p) => ({
	        kind: "image" as const,
	        url: p.url,
	        filename: p.filename,
	        file_id: p.file_id,
	        content_type: p.content_type,
	      })),
	      ...files.map((p) => ({
	        kind: "file" as const,
	        url: p.url,
	        filename: p.filename,
	        file_id: p.file_id,
	        content_type: p.content_type,
	        size_bytes: p.size_bytes,
	      })),
	    ],
	  )
	  if (imgs.length) activePreview.value = { kind: "images", messageId: userMsgId }
    await nextTick()
    scrollToBottom(false)

	  sending.value = true
    const controller = new AbortController()
    sendAbortController.value = controller
	  try {
	    const res = await chat({
      message: text,
      session_id: sessionId.value,
      provider: provider.value,
      role: role.value,
      project_id: activeProjectId.value > 0 ? activeProjectId.value : undefined,
      security_preset: securityPreset.value,
      enable_shell: enableShell.value,
      enable_write: enableWrite.value,
      enable_browser: enableBrowser.value,
      enable_dangerous: effectiveDangerous.value,
      show_reasoning: showReasoning.value,
      attachments: [
        ...imgs.map((p) => ({ kind: "image" as const, file_id: p.file_id, filename: p.filename, content_type: p.content_type })),
        ...files.map((p) => ({ kind: "file" as const, file_id: p.file_id, filename: p.filename, content_type: p.content_type })),
      ],
    }, { signal: controller.signal })
	    sessionId.value = res.session_id
	    lastEvents.value = res.events
    const urlFromEvents = extractDownloadUrlFromEvents(res.events)
    let assistantText = res.assistant
    if (urlFromEvents && !assistantText.includes("/api/files/")) {
      assistantText = `${assistantText}\n\n下载：${urlFromEvents}`.trim()
    }

    const msgId = push("assistant", assistantText)
    eventsByMessageId.value = { ...eventsByMessageId.value, [msgId]: Array.isArray(res.events) ? res.events : [] }
    const preview = extractPptPreviewFromEvents(res.events)
    if (preview) pptPreviewByMessageId.value = { ...pptPreviewByMessageId.value, [msgId]: preview }

    const quotePreview = extractQuotePreviewFromEvents(res.events)
    if (quotePreview) quotePreviewByMessageId.value = { ...quotePreviewByMessageId.value, [msgId]: quotePreview }

    const protoPreview = extractProtoPreviewFromEvents(res.events)
    if (protoPreview) protoPreviewByMessageId.value = { ...protoPreviewByMessageId.value, [msgId]: protoPreview }

    if (protoPreview) activePreview.value = { kind: "proto", messageId: msgId }
    else if (preview) activePreview.value = { kind: "ppt", messageId: msgId }
    else if (quotePreview) activePreview.value = { kind: "quote", messageId: msgId }
    else {
      const files = extractDownloadLinks(assistantText)
      if (files.length) activePreview.value = { kind: "files", messageId: msgId }
    }

    void hydrateFilePreviewsFromText(msgId, assistantText)

	    pendingImages.value = []
	    pendingFiles.value = []
	    uploadError.value = null
	    void refreshHistory()
	  } catch (e: any) {
	    if (handleUnauthorized(e)) return
      if (e?.code === "ERR_CANCELED" || String(e?.message || "").toLowerCase().includes("canceled")) {
        showToast("已取消")
        return
      }
      showToast(formatAxiosError(e))
	    push("assistant", `ERROR: ${formatAxiosError(e)}`)
  } finally {
    sending.value = false
    sendAbortController.value = null
  }
}

function cancelSend() {
  if (!sending.value) return
  sendAbortController.value?.abort()
}

	function reset() {
	  sessionId.value = undefined
	  messages.value = []
	  lastEvents.value = []
	  eventsByMessageId.value = {}
  skillDownloadById.value = {}
  skillError.value = null
  browserImg.value = null
  browserError.value = null
  pptPreviewByMessageId.value = {}
  quotePreviewByMessageId.value = {}
	  protoPreviewByMessageId.value = {}
  sheetPreviewByMessageId.value = {}
	  pendingImages.value = []
	  pendingFiles.value = []
	  uploadError.value = null
	  draggingFiles.value = false
    isNearBottom.value = true
	  _dragDepth = 0
	  activePreview.value = null
    reasoningPartsCacheByText.clear()
    reasoningPartsCacheById.clear()
	}

async function runSelectedSkill() {
  if (!selectedSkill.value) return
  const skill = selectedSkill.value
  docsBusy.value = true
  skillError.value = null
  skillDownloadById.value = { ...skillDownloadById.value, [skill.id]: null }
  try {
    const payload: any = cloneSkillPayload(skillPayloadById.value[skill.id] ?? skill.default_payload ?? {})
    const supportWorkspace =
      skill.endpoint.startsWith("/api/docs/") || skill.endpoint === "/api/prototype/generate"
    const projectParam = supportWorkspace ? { project_id: activeProjectId.value > 0 ? activeProjectId.value : 0 } : undefined
    const res = await runSkill(skill.endpoint, payload, projectParam)
    const downloadUrl = res?.download_url
    if (!downloadUrl) {
      skillError.value = "生成成功，但未返回下载链接（download_url）。"
      return
    }
    skillDownloadById.value = { ...skillDownloadById.value, [skill.id]: toAbsoluteUrl(downloadUrl) }
    const workspaceHint = (() => {
      const path = typeof res?.workspace_path === "string" ? res.workspace_path.trim() : ""
      if (!path) return ""
      const ctx = typeof res?.workspace_context_path === "string" ? res.workspace_context_path.trim() : ""
      const lines = [`已保存到工作区：${path}`]
      if (ctx) lines.push(`上下文：${ctx}`)
      return `\n\n${lines.join("\n")}`
    })()

    if (skill.endpoint === "/api/docs/ppt") {
      const title = typeof payload?.title === "string" ? payload.title.trim() : ""
      const slidesRaw: unknown[] = Array.isArray(payload?.slides) ? (payload.slides as unknown[]) : []
      const slides: PptSlidePreview[] = slidesRaw
        .map((slide): PptSlidePreview => {
          const s = (slide as any) ?? {}
          const st = typeof s.title === "string" ? s.title.trim() : ""
          const bulletsRaw: unknown[] = Array.isArray(s.bullets) ? (s.bullets as unknown[]) : []
          const bullets = bulletsRaw.map((b) => String(b)).filter((b) => b.trim())
          return { title: st, bullets }
        })
        .filter((s) => s.title || s.bullets.length)
      const coverImageUrl = typeof res?.preview_image_url === "string" ? toAbsoluteUrl(res.preview_image_url) : ""

      if (title && slides.length) {
        const hint = coverImageUrl
          ? "下方封面为真实渲染图，内容页卡片为提纲。"
          : "下方为提纲预览（最终样式以 PPTX 为准）。"
        const msgId = push("assistant", `已生成 PPT（PPTX）：${title}

下载：${downloadUrl}
${workspaceHint}

${hint}`)
        pptPreviewByMessageId.value = {
          ...pptPreviewByMessageId.value,
          [msgId]: { title, slides, coverImageUrl: coverImageUrl || undefined },
        }
        activePreview.value = { kind: "ppt", messageId: msgId }
      } else {
        const msgId = push("assistant", `已生成 PPT（PPTX）。

下载：${downloadUrl}${workspaceHint}`)
        activePreview.value = { kind: "files", messageId: msgId }
      }
      return
    }


    if (skill.endpoint === "/api/docs/quote" || skill.endpoint === "/api/docs/quote-xlsx") {
      const seller = typeof payload?.seller === "string" ? payload.seller.trim() : ""
      const buyer = typeof payload?.buyer === "string" ? payload.buyer.trim() : ""
      const currency = typeof payload?.currency === "string" ? payload.currency.trim() : "CNY"
      const note = typeof payload?.note === "string" ? payload.note.trim() : ""
      const itemsRaw: unknown[] = Array.isArray(payload?.items) ? (payload.items as unknown[]) : []
      const items: QuoteItemPreview[] = itemsRaw
        .map((it): QuoteItemPreview => {
          const v = (it as any) ?? {}
          const name = typeof v.name === "string" ? v.name.trim() : ""
          const quantity = Number(v.quantity ?? 0)
          const unit_price = Number(v.unit_price ?? 0)
          const unit = typeof v.unit === "string" ? v.unit.trim() : undefined
          return { name, quantity: Number.isFinite(quantity) ? quantity : 0, unit_price: Number.isFinite(unit_price) ? unit_price : 0, unit }
        })
        .filter((it) => it.name)
      if (!seller || !buyer || items.length === 0) {
        const msgId = push("assistant", `已生成报价单。\n\n下载：${downloadUrl}${workspaceHint}`)
        activePreview.value = { kind: "files", messageId: msgId }
        return
      }
      const total = items.reduce((sum, it) => sum + it.quantity * it.unit_price, 0)
      const kind: QuotePreview["kind"] = skill.endpoint === "/api/docs/quote-xlsx" ? "xlsx" : "docx"
      const msgId = push(
        "assistant",
        `已生成报价单（${kind.toUpperCase()}）。\n\n下载：${downloadUrl}${workspaceHint}\n\n下方为预览（按 JSON 渲染，最终样式以文件为准）。`,
      )
      quotePreviewByMessageId.value = {
        ...quotePreviewByMessageId.value,
        [msgId]: { kind, seller, buyer, currency: currency || "CNY", items, note: note || undefined, total },
      }
      activePreview.value = { kind: "quote", messageId: msgId }
      return
    }

    if (skill.endpoint === "/api/prototype/generate") {
      const project_name = typeof payload?.project_name === "string" ? payload.project_name.trim() : ""
      const pagesRaw: unknown[] = Array.isArray(payload?.pages) ? (payload.pages as unknown[]) : []
      const pages: ProtoPagePreview[] = pagesRaw
        .map((p): ProtoPagePreview => {
          const v = (p as any) ?? {}
          const title = typeof v.title === "string" ? v.title.trim() : ""
          const description = typeof v.description === "string" ? v.description.trim() : ""
          return { title, description: description || undefined }
        })
        .filter((p) => p.title)
      const previewUrl = typeof res?.preview_url === "string" ? res.preview_url.trim() : ""

      const msgId = push(
        "assistant",
        `已生成原型（HTML ZIP）。\n\n下载：${downloadUrl}${workspaceHint}\n\n下方为在线预览（最终效果以浏览器渲染为准）。`,
      )
      if (project_name && pages.length && previewUrl) {
        protoPreviewByMessageId.value = {
          ...protoPreviewByMessageId.value,
          [msgId]: { project_name, pages, preview_url: toAbsoluteUrl(previewUrl) },
        }
        activePreview.value = { kind: "proto", messageId: msgId }
      } else {
        activePreview.value = { kind: "files", messageId: msgId }
      }
      return
    }
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    skillError.value = formatAxiosError(e)
  } finally {
    docsBusy.value = false
  }
}

async function startBrowser() {
  if (!sessionId.value) return
  browserError.value = null
  try {
    await browserStart(sessionId.value)
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    browserError.value = formatAxiosError(e)
  }
}

async function navBrowser() {
  if (!sessionId.value) return
  browserError.value = null
  try {
    await browserNavigate(sessionId.value, browserUrl.value.trim())
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    browserError.value = formatAxiosError(e)
  }
}

async function shotBrowser() {
  if (!sessionId.value) return
  browserError.value = null
  try {
    const res = await browserScreenshot(sessionId.value)
    browserImg.value = `data:image/png;base64,${res.image_base64}`
  } catch (e: any) {
    if (handleUnauthorized(e)) return
    browserError.value = formatAxiosError(e)
  }
}

const appDomainCtx = {
  ...workspaceState,
  ...historyState,
  apiOk,
  sending,
  sendingElapsed,
  cancelSend,
  docsBusy,
  authReady,
  authBusy,
  authError,
  setupRequired,
  me,
  authToken,
  loginEmail,
  loginPassword,
  setupTeamName,
  setupName,
  setupEmail,
  setupPassword,
  activeTeamId,
  theme,
  vibe,
  densityMode,
  viewportWidth,
  viewportHeight,
  autoDensity,
  effectiveDensity,
  densityClass,
  densityLabel,
  provider,
  role,
  enableShell,
  enableWrite,
  enableBrowser,
  enableDangerous,
  showReasoning,
  securityPreset,
  leftNavSection,
  leftRailCollapsed,
  workspacePanel,
  agentProfiles,
  selectedAgentProfileId,
  activeAgentProfile,
  securityPresetLabel,
  dangerousTogglesLocked,
  dangerousBypassLocked,
  effectiveDangerous,
  skills,
  selectedSkillId,
  skillPayloadById,
  skillDownloadById,
  skillError,
  selectedSkill,
  selectedSkillPayload,
  selectedSkillPayloadJson,
  selectedSkillPayloadMarkdown,
  feishuManageMode,
  teamFeishuStats,
  teamDbExportBusy,
  teamDbExportError,
  teamDbExport,
  sessionId,
  input,
  messages,
  lastEvents,
  eventsByMessageId,
  lastStructuredTrace,
  showTrace,
  showLeft,
  showRight,
  showTopMenu,
  showTeamCenter,
  toastText,
  browserUrl,
  browserImg,
  browserError,
  chatBodyRef,
  downloadsByMessageId,
  pptPreviewByMessageId,
  quotePreviewByMessageId,
  protoPreviewByMessageId,
  sheetPreviewByMessageId,
  docPreviewByMessageId,
  readmePreviewByProjectId,
  readmeBusyByProjectId,
  readmeErrorByProjectId,
  activePreview,
  activePpt,
  activeQuote,
  activeProto,
  activeSheet,
  activeDoc,
  activeReadme,
  activeReadmeBusy,
  activeReadmeError,
  activeImages,
  activeFileDownloads,
  imagePickerRef,
  filePickerRef,
  composerInputRef,
  pendingImages,
  pendingFiles,
  uploadingImages,
  uploadingFiles,
  uploadError,
  draggingFiles,
  isNearBottom,
  showScrollToBottom,
  refreshViewportSize,
  switchLeftNav,
  applyAgentProfile,
  cloneSkillPayload,
  _payloadText,
  _payloadBullets,
  payloadToMarkdown,
  showToast,
  formatTime,
  formatIsoTime,
  formatBytes,
  renderMarkdown,
  assistantParts,
  applyQuickPrompt,
  _trimTrailingPunctuation,
  toAbsoluteUrl,
  extractDownloadLinks,
  extractDownloadUrlFromEvents,
  extractPptPreviewFromEvents,
  extractQuotePreviewFromEvents,
  extractProtoPreviewFromEvents,
  summarizeTrace,
  formatToolToggleSet,
  traceToolHint,
  structuredTrace,
  _fileKindFromId,
  _fileIdFromDownload,
  formatMoney,
  copyToClipboard,
  toggleTheme,
  formatApiDetail,
  formatAxiosError,
  handleUnauthorized,
  applyAuth,
  loadBuiltinSkills,
  resetSelectedSkillPayload,
  historyMessageContent,
  historyMessageDownloads,
  historyEventsOf,
  openHistorySession,
  loadHistoryIntoChat,
  removeHistorySession,
  onSwitchProject,
  switchWorkspaceProject,
  saveTeamWorkspace,
  clearTeamWorkspace,
  openProjectManager,
  openProjectManagerForProject,
  openProjectManagerForNewProject,
  openProjectReadme,
  toggleProjectTree,
  selectTeamProject,
  newTeamProject,
  quickImportTeamProjects,
  selectTeamRequirement,
  newTeamRequirement,
  quickSetRequirementStatus,
  saveTeamRequirement,
  removeTeamRequirement,
  selectTeamFeishuWebhook,
  newTeamFeishuWebhook,
  refreshTeamFeishuWebhooks,
  importTeamFeishuPreset,
  toggleTeamFeishuEnabled,
  setAllTeamFeishuEnabled,
  saveTeamFeishuWebhook,
  removeTeamFeishuWebhook,
  saveTeamProject,
  removeTeamProject,
  selectTeamSkill,
  newTeamSkill,
  saveTeamSkill,
  aiGenerateTeamSkill,
  removeTeamSkill,
  exportTeamDbMd,
  loadAfterAuth,
  logout,
  submitLogin,
  submitSetup,
  onSwitchTeam,
  push,
  onChatBodyScroll,
  scrollToBottom,
  pickImages,
  pickFiles,
  removePendingImage,
  removePendingFile,
  onPickImages,
  onPickFiles,
  onComposerPaste,
  onComposerDrop,
  onChatDragEnter,
  onChatDragOver,
  onChatDragLeave,
  onChatDrop,
  onComposerKeydown,
  send,
  reset,
  runSelectedSkill,
  startBrowser,
  navBrowser,
  shotBrowser,
}

onMounted(() => {
  refreshViewportSize()
  window.addEventListener("resize", refreshViewportSize, { passive: true })
})

onUnmounted(() => {
  window.removeEventListener("resize", refreshViewportSize)
})

onMounted(async () => {
  const healthTask = withTimeout(health(), 4500, "health")
    .then(() => {
      apiOk.value = true
    })
    .catch(() => {
      apiOk.value = false
    })

  const authTask = withTimeout(authStatus(), 4500, "auth")
    .then((st) => {
      setupRequired.value = !!st.setup_required
    })
    .catch((e: any) => {
      authError.value = formatAxiosError(e)
    })

  await Promise.allSettled([healthTask, authTask])

  const token = authToken.value?.trim()
	  if (token) {
	    setAuthToken(token)
	    try {
	      me.value = await getMe()
	      activeTeamId.value = me.value.active_team.id
	      const email = normalizeEmail(me.value?.user?.email || "")
	      if (email) {
	        setLastTeamIdForEmail(email, Number(me.value?.active_team?.id || 0))
	        markTeamOnboarded(email)
	      }
	    } catch {
	      authToken.value = null
	      localStorage.removeItem("aistaff_token")
	      setAuthToken(null)
      me.value = null
    }
  }

  authReady.value = true
  if (me.value) await loadAfterAuth()
})
</script>

<style src="./App.css"></style>
