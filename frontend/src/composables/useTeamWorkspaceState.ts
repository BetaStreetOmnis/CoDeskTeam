import { computed, ref, watch, type Ref } from "vue"

import {
  acceptTeamRequirementDelivery,
  createTeamFeishuWebhook,
  createTeamProject,
  createTeamRequirement,
  createTeamSkill,
  deleteTeamFeishuWebhook,
  deleteTeamProject,
  deleteTeamRequirement,
  deleteTeamSkill,
  getTeamSettings,
  getTeamProjectTree,
  getTeamWorkspaceTree,
  listTeamFeishuWebhooks,
  listTeamProjects,
  listTeamRequirements,
  listTeamSkills,
  rejectTeamRequirementDelivery,
  updateTeamFeishuWebhook,
  updateTeamProject,
  updateTeamRequirement,
  updateTeamSkill,
} from "../api"
import type {
  MeResponse,
  TeamFeishuWebhook,
  TeamProject,
  TeamProjectTreeNode,
  TeamRequirement,
  TeamSettings,
  TeamSkill,
} from "../api"

type ErrorFormatter = (error: any) => string

type Options = {
  me: Ref<MeResponse | null>
  formatError: ErrorFormatter
  handleUnauthorized: (error: any) => boolean
  showToast?: (text: string) => void
  onActiveProjectReset?: () => void
}

type ProjectTreeFlatItem = {
  key: string
  node: TeamProjectTreeNode
  level: number
}

function projectStorageKey(teamId: number) {
  return `aistaff_project_${teamId}`
}

function loadStoredProjectId(teamId: number | null | undefined): number {
  if (!teamId) return 0
  const raw = localStorage.getItem(projectStorageKey(teamId)) || "0"
  const n = Number(raw)
  if (!Number.isFinite(n)) return 0
  return n > 0 ? Math.floor(n) : 0
}

export function useTeamWorkspaceState({ me, formatError, handleUnauthorized, showToast, onActiveProjectReset }: Options) {
  const teamSkills = ref<TeamSkill[]>([])
  const teamSkillsBusy = ref(false)
  const teamSkillsError = ref<string | null>(null)
  const selectedTeamSkillId = ref<number | "new" | null>(null)
  const teamSkillForm = ref<{ name: string; description: string; content: string; enabled: boolean }>({
    name: "",
    description: "",
    content: "",
    enabled: true,
  })

  const teamProjects = ref<TeamProject[]>([])
  const teamProjectsBusy = ref(false)
  const teamProjectsError = ref<string | null>(null)
  const projectSearch = ref("")
  const activeProjectId = ref(0)
  const previousProjectId = ref(0)
  const showProjectModal = ref(false)
  const selectedTeamProjectId = ref<number | "new" | null>(null)
  const teamProjectForm = ref<{ name: string; slug: string; path: string; enabled: boolean }>({
    name: "",
    slug: "",
    path: "",
    enabled: true,
  })
  const projectTreeById = ref<Record<number, TeamProjectTreeNode[]>>({})
  const projectTreeBusyById = ref<Record<number, boolean>>({})
  const projectTreeErrorById = ref<Record<number, string | null>>({})
  const projectTreeExpandedById = ref<Record<number, boolean>>({})
  const projectTreeOpenByKey = ref<Record<string, boolean>>({})
  const projectTreeLoadingByKey = ref<Record<string, boolean>>({})

  const teamSettings = ref<TeamSettings | null>(null)
  const teamSettingsBusy = ref(false)
  const teamSettingsError = ref<string | null>(null)
  const teamWorkspaceDraft = ref("")

  const teamFeishuWebhooks = ref<TeamFeishuWebhook[]>([])
  const teamFeishuBusy = ref(false)
  const teamFeishuError = ref<string | null>(null)
  const selectedTeamFeishuId = ref<number | "new" | null>(null)
  const teamFeishuForm = ref<{ name: string; webhook_url: string; verification_token: string; enabled: boolean }>({
    name: "",
    webhook_url: "",
    verification_token: "",
    enabled: true,
  })

  const teamRequirements = ref<TeamRequirement[]>([])
  const teamRequirementsBusy = ref(false)
  const teamRequirementsError = ref<string | null>(null)
  const selectedTeamRequirementId = ref<number | "new" | null>(null)
  const requirementSearch = ref("")
  const requirementStatusFilter = ref<"" | "incoming" | "todo" | "in_progress" | "done" | "blocked">("")
  const requirementPriorityFilter = ref<"" | "low" | "medium" | "high" | "urgent">("")
  const teamRequirementForm = ref<{
    project_id: number
    source_team: string
    title: string
    description: string
    status: "incoming" | "todo" | "in_progress" | "done" | "blocked"
    priority: "low" | "medium" | "high" | "urgent"
    delivery_target_team_id: number
  }>({
    project_id: 0,
    source_team: "",
    title: "",
    description: "",
    status: "incoming",
    priority: "medium",
    delivery_target_team_id: 0,
  })

  const canEditTeamSkills = computed(() => {
    const role = me.value?.active_team?.role
    return role === "owner" || role === "admin"
  })
  const canEditTeamProjects = computed(() => canEditTeamSkills.value)
  const canEditTeamFeishu = computed(() => canEditTeamProjects.value)
  const canEditTeamRequirements = computed(() => canEditTeamProjects.value)

  const activeProject = computed(() => teamProjects.value.find((p) => p.id === activeProjectId.value) ?? null)
  const selectedTeamFeishu = computed(() => {
    if (typeof selectedTeamFeishuId.value !== "number") return null
    return teamFeishuWebhooks.value.find((item) => item.id === selectedTeamFeishuId.value) ?? null
  })
  const selectedTeamRequirement = computed(() => {
    if (typeof selectedTeamRequirementId.value !== "number") return null
    return teamRequirements.value.find((item) => item.id === selectedTeamRequirementId.value) ?? null
  })
  const teamWorkspacePath = computed(() => {
    const raw = teamSettings.value?.workspace_path ?? null
    const t = typeof raw === "string" ? raw.trim() : ""
    return t || null
  })
  const workspaceRootPath = computed(() => {
    const raw = teamSettings.value?.workspace_root ?? null
    const t = typeof raw === "string" ? raw.trim() : ""
    return t || null
  })
  const activeWorkspaceLabel = computed(() => activeProject.value?.name || (teamWorkspacePath.value ? "团队工作区" : "默认工作区"))
  const activeWorkspacePath = computed(
    () => activeProject.value?.path || workspaceRootPath.value || teamWorkspacePath.value || "服务端 JETLINKS_AI_WORKSPACE（默认）",
  )

  function projectTreeFolderKey(projectId: number, relPath: string): string {
    const pid = Number(projectId)
    const normalized = String(relPath || "").trim() || "."
    return `${pid}:${normalized}`
  }

  function _setProjectTreeBusy(projectId: number, busy: boolean) {
    projectTreeBusyById.value = { ...projectTreeBusyById.value, [projectId]: busy }
  }

  function _setProjectTreeError(projectId: number, error: string | null) {
    projectTreeErrorById.value = { ...projectTreeErrorById.value, [projectId]: error }
  }

  function _clearProjectTreeState() {
    projectTreeById.value = {}
    projectTreeBusyById.value = {}
    projectTreeErrorById.value = {}
    projectTreeExpandedById.value = {}
    projectTreeOpenByKey.value = {}
    projectTreeLoadingByKey.value = {}
  }

  function _replaceProjectFolderChildren(
    nodes: TeamProjectTreeNode[],
    targetRelPath: string,
    nextChildren: TeamProjectTreeNode[],
  ): TeamProjectTreeNode[] {
    return nodes.map((node) => {
      if (node.rel_path === targetRelPath) {
        return {
          ...node,
          has_children: node.has_children || nextChildren.length > 0,
          children: nextChildren,
        }
      }
      if (node.node_type !== "dir" || !node.children?.length) return node
      return {
        ...node,
        children: _replaceProjectFolderChildren(node.children, targetRelPath, nextChildren),
      }
    })
  }

  async function loadProjectTree(projectId: number, subPath?: string) {
    const pid = Number(projectId)
    if (!Number.isFinite(pid) || pid < 0) return
    const isWorkspace = pid === 0

    if (!subPath) {
      _setProjectTreeBusy(pid, true)
      _setProjectTreeError(pid, null)
      try {
        const nodes = isWorkspace
          ? await getTeamWorkspaceTree({ max_depth: 2, max_entries: 120 })
          : await getTeamProjectTree(pid, { max_depth: 2, max_entries: 120 })
        projectTreeById.value = { ...projectTreeById.value, [pid]: nodes }
      } catch (error: any) {
        if (handleUnauthorized(error)) return
        _setProjectTreeError(pid, formatError(error))
      } finally {
        _setProjectTreeBusy(pid, false)
      }
      return
    }

    const key = projectTreeFolderKey(pid, subPath)
    projectTreeLoadingByKey.value = { ...projectTreeLoadingByKey.value, [key]: true }
    try {
      const nodes = isWorkspace
        ? await getTeamWorkspaceTree({ sub_path: subPath, max_depth: 1, max_entries: 120 })
        : await getTeamProjectTree(pid, { sub_path: subPath, max_depth: 1, max_entries: 120 })
      const current = projectTreeById.value[pid] ?? []
      projectTreeById.value = {
        ...projectTreeById.value,
        [pid]: _replaceProjectFolderChildren(current, subPath, nodes),
      }
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      _setProjectTreeError(pid, formatError(error))
    } finally {
      projectTreeLoadingByKey.value = { ...projectTreeLoadingByKey.value, [key]: false }
    }
  }

  async function toggleProjectTree(projectId: number) {
    const pid = Number(projectId)
    if (!Number.isFinite(pid) || pid < 0) return
    const expanded = !!projectTreeExpandedById.value[pid]
    projectTreeExpandedById.value = { ...projectTreeExpandedById.value, [pid]: !expanded }
    if (expanded) return
    if (!(pid in projectTreeById.value)) {
      await loadProjectTree(pid)
    }
  }

  function isProjectTreeFolderOpen(projectId: number, relPath: string): boolean {
    return !!projectTreeOpenByKey.value[projectTreeFolderKey(projectId, relPath)]
  }

  function isProjectTreeFolderBusy(projectId: number, relPath: string): boolean {
    return !!projectTreeLoadingByKey.value[projectTreeFolderKey(projectId, relPath)]
  }

  async function toggleProjectTreeFolder(projectId: number, node: TeamProjectTreeNode) {
    if (node.node_type !== "dir" || !node.has_children) return
    const key = projectTreeFolderKey(projectId, node.rel_path)
    const nextOpen = !projectTreeOpenByKey.value[key]
    projectTreeOpenByKey.value = { ...projectTreeOpenByKey.value, [key]: nextOpen }
    if (!nextOpen) return
    if ((node.children ?? []).length > 0) return
    await loadProjectTree(projectId, node.rel_path)
  }

  function flattenProjectTree(projectId: number): ProjectTreeFlatItem[] {
    const pid = Number(projectId)
    if (!Number.isFinite(pid) || pid < 0) return []
    const roots = projectTreeById.value[pid] ?? []
    const rows: ProjectTreeFlatItem[] = []

    const walk = (nodes: TeamProjectTreeNode[], level: number) => {
      for (const node of nodes) {
        rows.push({ key: `${pid}:${node.rel_path || node.name}`, node, level })
        if (node.node_type === "dir" && node.children?.length && isProjectTreeFolderOpen(pid, node.rel_path)) {
          walk(node.children, level + 1)
        }
      }
    }

    walk(roots, 0)
    return rows
  }

  function projectNameFromId(projectId: number | null | undefined): string {
    const pid = typeof projectId === "number" ? projectId : null
    if (!pid) return teamWorkspacePath.value ? "团队工作区" : "默认工作区"
    return teamProjects.value.find((p) => p.id === pid)?.name ?? `项目#${pid}`
  }

  function requirementStatusLabel(status: TeamRequirement["status"]): string {
    if (status === "todo") return "待处理"
    if (status === "in_progress") return "处理中"
    if (status === "done") return "已完成"
    if (status === "blocked") return "阻塞"
    return "新交付"
  }

  function requirementPriorityLabel(priority: TeamRequirement["priority"]): string {
    if (priority === "low") return "低优"
    if (priority === "high") return "高优"
    if (priority === "urgent") return "紧急"
    return "中优"
  }

  const filteredTeamProjects = computed(() => {
    const q = projectSearch.value.trim().toLowerCase()
    if (!q) return teamProjects.value
    return teamProjects.value.filter((p) => {
      const hay = [p.name || "", p.slug || "", p.path || ""].join(" ").toLowerCase()
      return hay.includes(q)
    })
  })

  const filteredTeamRequirements = computed(() => {
    const q = requirementSearch.value.trim().toLowerCase()
    const status = requirementStatusFilter.value
    const priority = requirementPriorityFilter.value
    return teamRequirements.value.filter((item) => {
      if (status && item.status !== status) return false
      if (priority && item.priority !== priority) return false
      if (!q) return true
      const hay = [
        item.title || "",
        item.description || "",
        item.source_team || "",
        item.delivery?.from_team_name || "",
        item.delivery?.by_user_name || "",
        projectNameFromId(item.project_id),
        requirementStatusLabel(item.status),
        requirementPriorityLabel(item.priority),
      ]
        .join(" ")
        .toLowerCase()
      return hay.includes(q)
    })
  })

  const requirementStats = computed(() => {
    const stats = {
      total: teamRequirements.value.length,
      incoming: 0,
      todo: 0,
      in_progress: 0,
      done: 0,
      blocked: 0,
    }
    for (const item of teamRequirements.value) {
      if (item.status === "incoming") stats.incoming += 1
      else if (item.status === "todo") stats.todo += 1
      else if (item.status === "in_progress") stats.in_progress += 1
      else if (item.status === "done") stats.done += 1
      else if (item.status === "blocked") stats.blocked += 1
    }
    return stats
  })

  function resetRequirementFilters() {
    requirementSearch.value = ""
    requirementStatusFilter.value = ""
    requirementPriorityFilter.value = ""
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

  watch(
    [selectedTeamRequirementId, () => teamRequirementForm.value.delivery_target_team_id, () => me.value?.active_team?.name],
    ([selectedId, targetTeamId, activeTeamName]) => {
      if (selectedId !== "new") return
      if (Number(targetTeamId) <= 0) return
      const name = String(activeTeamName || "").trim()
      if (!name) return
      teamRequirementForm.value.source_team = name
    },
  )

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

  async function refreshTeamSkills() {
    teamSkillsBusy.value = true
    teamSkillsError.value = null
    try {
      const items = await listTeamSkills()
      teamSkills.value = items

      const current = selectedTeamSkillId.value
      if (current === "new") return

      const preferredId = typeof current === "number" ? current : null
      const found = preferredId ? items.find((s) => s.id === preferredId) : null
      if (found) {
        selectTeamSkill(found)
        return
      }

      if (items.length > 0) {
        const first = items[0]
        if (first) selectTeamSkill(first)
      } else if (canEditTeamSkills.value) {
        newTeamSkill()
      } else {
        selectedTeamSkillId.value = null
      }
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamSkillsError.value = formatError(error)
    } finally {
      teamSkillsBusy.value = false
    }
  }

  async function refreshTeamSettings() {
    teamSettingsBusy.value = true
    teamSettingsError.value = null
    try {
      const settings = await getTeamSettings()
      teamSettings.value = settings
      teamWorkspaceDraft.value = (settings.workspace_path || "").trim()
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamSettingsError.value = formatError(error)
    } finally {
      teamSettingsBusy.value = false
    }
  }

  async function refreshTeamProjects() {
    teamProjectsBusy.value = true
    teamProjectsError.value = null
    try {
      const items = await listTeamProjects()
      teamProjects.value = items
      _clearProjectTreeState()

      if (activeProjectId.value > 0) {
        const found = items.find((p) => p.id === activeProjectId.value && p.enabled)
        if (!found) {
          activeProjectId.value = 0
          previousProjectId.value = 0
        }
      }

      const current = selectedTeamProjectId.value
      if (current === "new") return

      const preferredId = typeof current === "number" ? current : null
      const found = preferredId ? items.find((p) => p.id === preferredId) : null
      if (found) {
        selectTeamProject(found)
        return
      }

      if (items.length > 0) {
        const first = items[0]
        if (first) selectTeamProject(first)
      } else if (canEditTeamProjects.value) {
        newTeamProject()
      } else {
        selectedTeamProjectId.value = null
      }
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamProjectsError.value = formatError(error)
    } finally {
      teamProjectsBusy.value = false
    }
  }

  async function refreshTeamRequirements() {
    teamRequirementsBusy.value = true
    teamRequirementsError.value = null
    try {
      const items = await listTeamRequirements()
      teamRequirements.value = items

      const current = selectedTeamRequirementId.value
      if (current === "new") return

      const preferredId = typeof current === "number" ? current : null
      const found = preferredId ? items.find((item) => item.id === preferredId) : null
      if (found) {
        selectTeamRequirement(found)
        return
      }

      if (items.length > 0) {
        const first = items[0]
        if (first) selectTeamRequirement(first)
      } else if (canEditTeamRequirements.value) {
        newTeamRequirement()
      } else {
        selectedTeamRequirementId.value = null
      }
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamRequirementsError.value = formatError(error)
    } finally {
      teamRequirementsBusy.value = false
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
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamFeishuError.value = formatError(error)
    } finally {
      teamFeishuBusy.value = false
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
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamRequirementsError.value = formatError(error)
    } finally {
      teamRequirementsBusy.value = false
    }
  }

  async function acceptRequirementDelivery(item: TeamRequirement) {
    if (!canEditTeamRequirements.value) return
    if (!item.delivery || item.delivery.state !== "pending") return
    teamRequirementsBusy.value = true
    teamRequirementsError.value = null
    try {
      await acceptTeamRequirementDelivery(item.id)
      await refreshTeamRequirements()
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamRequirementsError.value = formatError(error)
    } finally {
      teamRequirementsBusy.value = false
    }
  }

  async function rejectRequirementDelivery(item: TeamRequirement) {
    if (!canEditTeamRequirements.value) return
    if (!item.delivery || item.delivery.state !== "pending") return
    const ok = confirm(`确定拒绝交付「${item.title || item.id}」吗？`)
    if (!ok) return
    teamRequirementsBusy.value = true
    teamRequirementsError.value = null
    try {
      await rejectTeamRequirementDelivery(item.id)
      await refreshTeamRequirements()
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamRequirementsError.value = formatError(error)
    } finally {
      teamRequirementsBusy.value = false
    }
  }

  async function saveTeamRequirement() {
    if (!canEditTeamRequirements.value) return
    teamRequirementsError.value = null

    const activeTeamId = me.value?.active_team?.id
    const deliveryTargetId =
      teamRequirementForm.value.delivery_target_team_id > 0 ? teamRequirementForm.value.delivery_target_team_id : null
    const delivery =
      activeTeamId && deliveryTargetId && Number(deliveryTargetId) !== Number(activeTeamId)
        ? { target_team_id: Number(deliveryTargetId) }
        : null

    const form = {
      project_id: teamRequirementForm.value.project_id > 0 ? teamRequirementForm.value.project_id : null,
      source_team: (delivery ? me.value?.active_team?.name ?? "" : teamRequirementForm.value.source_team).trim(),
      title: teamRequirementForm.value.title.trim(),
      description: teamRequirementForm.value.description.trim(),
      status: teamRequirementForm.value.status,
      priority: teamRequirementForm.value.priority,
      delivery,
    }

    if (!form.title) {
      teamRequirementsError.value = "请填写“需求标题”。"
      return
    }

    teamRequirementsBusy.value = true
    try {
      if (selectedTeamRequirementId.value === "new") {
        const created = await createTeamRequirement(form)
        if (activeTeamId && created.team_id !== activeTeamId) {
          showToast?.(`已发起交付到团队「${created.team_id}」，请切换目标团队接收/拒绝。`)
          newTeamRequirement()
          return
        }
        await refreshTeamRequirements()
        const found = teamRequirements.value.find((item) => item.id === created.id)
        if (found) selectTeamRequirement(found)
      } else if (typeof selectedTeamRequirementId.value === "number") {
        const updated = await updateTeamRequirement(selectedTeamRequirementId.value, form)
        await refreshTeamRequirements()
        const found = teamRequirements.value.find((item) => item.id === updated.id)
        if (found) selectTeamRequirement(found)
      }
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamRequirementsError.value = formatError(error)
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
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamRequirementsError.value = formatError(error)
    } finally {
      teamRequirementsBusy.value = false
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
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamFeishuError.value = formatError(error)
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
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamFeishuError.value = formatError(error)
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
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamProjectsError.value = formatError(error)
    } finally {
      teamProjectsBusy.value = false
    }
  }

  async function removeTeamProject() {
    if (!canEditTeamProjects.value) return
    if (typeof selectedTeamProjectId.value !== "number") return
    const id = selectedTeamProjectId.value
    const project = teamProjects.value.find((x) => x.id === id)
    const ok = confirm(`确定删除项目「${project?.name ?? id}」吗？`)
    if (!ok) return

    teamProjectsBusy.value = true
    teamProjectsError.value = null
    try {
      await deleteTeamProject(id)
      if (activeProjectId.value === id) {
        activeProjectId.value = 0
        previousProjectId.value = 0
        onActiveProjectReset?.()
      }
      selectedTeamProjectId.value = null
      await refreshTeamProjects()
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamProjectsError.value = formatError(error)
    } finally {
      teamProjectsBusy.value = false
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
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamSkillsError.value = formatError(error)
    } finally {
      teamSkillsBusy.value = false
    }
  }

  async function removeTeamSkill() {
    if (!canEditTeamSkills.value) return
    if (typeof selectedTeamSkillId.value !== "number") return
    const id = selectedTeamSkillId.value
    const skill = teamSkills.value.find((x) => x.id === id)
    const ok = confirm(`确定删除团队技能「${skill?.name ?? id}」吗？`)
    if (!ok) return

    teamSkillsBusy.value = true
    teamSkillsError.value = null
    try {
      await deleteTeamSkill(id)
      selectedTeamSkillId.value = null
      await refreshTeamSkills()
    } catch (error: any) {
      if (handleUnauthorized(error)) return
      teamSkillsError.value = formatError(error)
    } finally {
      teamSkillsBusy.value = false
    }
  }

  async function refreshWorkspace() {
    await Promise.all([refreshTeamSettings(), refreshTeamProjects(), refreshTeamRequirements()])
  }

  watch(
    () => me.value?.active_team?.id,
    (teamId) => {
      _clearProjectTreeState()
      const stored = loadStoredProjectId(teamId)
      activeProjectId.value = stored
      previousProjectId.value = stored
    },
  )

  watch(activeProjectId, (id) => {
    const teamId = me.value?.active_team?.id
    if (!teamId) return
    localStorage.setItem(projectStorageKey(teamId), String(id || 0))
  })

  return {
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
    canEditTeamSkills,
    canEditTeamProjects,
    canEditTeamFeishu,
    canEditTeamRequirements,
    activeProject,
    selectedTeamFeishu,
    selectedTeamRequirement,
    teamWorkspacePath,
    workspaceRootPath,
    activeWorkspaceLabel,
    activeWorkspacePath,
    filteredTeamProjects,
    filteredTeamRequirements,
    requirementStats,
    projectNameFromId,
    requirementStatusLabel,
    requirementPriorityLabel,
    resetRequirementFilters,
    selectTeamProject,
    newTeamProject,
    toggleProjectTree,
    flattenProjectTree,
    toggleProjectTreeFolder,
    isProjectTreeFolderOpen,
    isProjectTreeFolderBusy,
    selectTeamRequirement,
    newTeamRequirement,
    selectTeamFeishuWebhook,
    newTeamFeishuWebhook,
    selectTeamSkill,
    newTeamSkill,
    quickSetRequirementStatus,
    acceptRequirementDelivery,
    rejectRequirementDelivery,
    saveTeamRequirement,
    removeTeamRequirement,
    saveTeamFeishuWebhook,
    removeTeamFeishuWebhook,
    saveTeamProject,
    removeTeamProject,
    saveTeamSkill,
    removeTeamSkill,
    refreshTeamSkills,
    refreshTeamSettings,
    refreshTeamProjects,
    refreshTeamRequirements,
    refreshTeamFeishuWebhooks,
    refreshWorkspace,
  }
}
