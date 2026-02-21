import axios from "axios"

export type TeamSkill = {
  id: number
  team_id: number
  name: string
  description: string
  content: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export type TeamSkillAIDraftRequest = {
  idea: string
  name?: string
  description?: string
  draft?: string
  model?: string
}

export type TeamSkillAIDraftResponse = {
  name: string
  description: string
  content: string
}

export type TeamProject = {
  id: number
  team_id: number
  name: string
  slug: string
  path: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export type TeamProjectTreeNode = {
  name: string
  rel_path: string
  node_type: "dir" | "file"
  has_children: boolean
  children: TeamProjectTreeNode[]
}

export type TeamProjectReadme = {
  exists: boolean
  filename?: string | null
  rel_path?: string | null
  content?: string | null
  truncated?: boolean
}

export type TeamProjectCandidate = {
  name: string
  path: string
  slug: string
  root: string
  detected_by: string
  already_added: boolean
}

export type TeamProjectImportSkipped = {
  path: string
  reason: string
}

export type TeamProjectImportResult = {
  created: TeamProject[]
  skipped: TeamProjectImportSkipped[]
}

export type TeamSettings = {
  workspace_path: string | null
  workspace_root?: string | null
}

export type TeamFeishuWebhook = {
  id: number
  team_id: number
  name: string
  hook: string
  callback_url: string
  webhook_url: string
  verification_token: string | null
  enabled: boolean
  created_at: string
  updated_at: string
}

export type TeamRequirementDelivery = {
  to_team_id: number
  from_team_id: number
  from_team_name: string | null
  by_user_id: number | null
  by_user_name: string | null
  state: "pending" | "accepted" | "rejected"
  decided_by_user_id: number | null
  decided_by_user_name: string | null
  decided_at: string | null
}

export type TeamRequirement = {
  id: number
  team_id: number
  project_id: number | null
  source_team: string
  title: string
  description: string
  status: "incoming" | "todo" | "in_progress" | "done" | "blocked"
  priority: "low" | "medium" | "high" | "urgent"
  delivery?: TeamRequirementDelivery | null
  created_at: string
  updated_at: string
}

export type TeamMember = {
  user_id: number
  email: string
  name: string
  role: string
  joined_at: string
}

export type TeamInvite = {
  id: number
  team_id: number
  email: string | null
  role: string
  token: string
  created_by: number | null
  created_at: string
  expires_at: string
  used_at: string | null
  used_by: number | null
}

export type TeamDbExport = {
  ok: boolean
  updated_at: string
  workspace_root: string
  workspace_path: string
  bytes: number
  filename: string
}

export async function listTeamSkills(): Promise<TeamSkill[]> {
  const res = await axios.get("/api/team/skills")
  return res.data as TeamSkill[]
}

export async function createTeamSkill(req: {
  name: string
  description?: string
  content: string
  enabled?: boolean
}): Promise<TeamSkill> {
  const res = await axios.post("/api/team/skills", req)
  return res.data as TeamSkill
}

export async function updateTeamSkill(
  id: number,
  req: { name?: string; description?: string; content?: string; enabled?: boolean },
): Promise<TeamSkill> {
  const res = await axios.put(`/api/team/skills/${id}`, req)
  return res.data as TeamSkill
}

export async function deleteTeamSkill(id: number): Promise<void> {
  await axios.delete(`/api/team/skills/${id}`)
}

export async function aiDraftTeamSkill(req: TeamSkillAIDraftRequest): Promise<TeamSkillAIDraftResponse> {
  const res = await axios.post("/api/team/skills/ai-draft", req)
  return res.data as TeamSkillAIDraftResponse
}

export async function listTeamProjects(): Promise<TeamProject[]> {
  const res = await axios.get("/api/team/projects")
  return res.data as TeamProject[]
}

export async function createTeamProject(req: {
  name: string
  slug?: string
  path: string
  enabled?: boolean
}): Promise<TeamProject> {
  const res = await axios.post("/api/team/projects", req)
  return res.data as TeamProject
}

export async function updateTeamProject(
  id: number,
  req: { name?: string; slug?: string; path?: string; enabled?: boolean },
): Promise<TeamProject> {
  const res = await axios.put(`/api/team/projects/${id}`, req)
  return res.data as TeamProject
}

export async function deleteTeamProject(id: number): Promise<void> {
  await axios.delete(`/api/team/projects/${id}`)
}

export async function discoverTeamProjects(params?: {
  max_entries?: number
  include_hidden?: boolean
  include_added?: boolean
}): Promise<TeamProjectCandidate[]> {
  const res = await axios.get("/api/team/projects/discover", { params })
  return res.data as TeamProjectCandidate[]
}

export async function importTeamProjects(req: {
  paths: string[]
  enabled?: boolean
}): Promise<TeamProjectImportResult> {
  const res = await axios.post("/api/team/projects/import", req)
  return res.data as TeamProjectImportResult
}

export async function getTeamProjectTree(
  projectId: number,
  params?: { sub_path?: string; max_depth?: number; max_entries?: number; show_hidden?: boolean },
): Promise<TeamProjectTreeNode[]> {
  const res = await axios.get(`/api/team/projects/${projectId}/tree`, { params })
  return res.data as TeamProjectTreeNode[]
}

export async function getTeamProjectReadme(projectId: number): Promise<TeamProjectReadme> {
  const res = await axios.get(`/api/team/projects/${projectId}/readme`)
  return res.data as TeamProjectReadme
}

export async function getTeamWorkspaceReadme(): Promise<TeamProjectReadme> {
  const res = await axios.get("/api/team/workspace/readme")
  return res.data as TeamProjectReadme
}

export async function getTeamWorkspaceTree(params?: {
  sub_path?: string
  max_depth?: number
  max_entries?: number
  show_hidden?: boolean
}): Promise<TeamProjectTreeNode[]> {
  const res = await axios.get("/api/team/workspace/tree", { params })
  return res.data as TeamProjectTreeNode[]
}

export async function getTeamSettings(): Promise<TeamSettings> {
  const res = await axios.get("/api/team/settings")
  return res.data as TeamSettings
}

export async function updateTeamSettings(req: { workspace_path?: string | null }): Promise<TeamSettings> {
  const res = await axios.put("/api/team/settings", req)
  return res.data as TeamSettings
}

export async function exportTeamDbMarkdown(params?: { project_id?: number | null }): Promise<TeamDbExport> {
  const project_id = params?.project_id != null && Number(params.project_id) > 0 ? Number(params.project_id) : undefined
  const res = await axios.post("/api/team/export-md", {}, project_id ? { params: { project_id } } : undefined)
  return res.data as TeamDbExport
}


export async function listTeamFeishuWebhooks(): Promise<TeamFeishuWebhook[]> {
  const res = await axios.get("/api/team/feishu/webhooks")
  return res.data as TeamFeishuWebhook[]
}

export async function createTeamFeishuWebhook(req: {
  name: string
  webhook_url: string
  verification_token?: string | null
  enabled?: boolean
}): Promise<TeamFeishuWebhook> {
  const res = await axios.post("/api/team/feishu/webhooks", req)
  return res.data as TeamFeishuWebhook
}

export async function updateTeamFeishuWebhook(
  id: number,
  req: { name?: string; webhook_url?: string; verification_token?: string | null; enabled?: boolean },
): Promise<TeamFeishuWebhook> {
  const res = await axios.put(`/api/team/feishu/webhooks/${id}`, req)
  return res.data as TeamFeishuWebhook
}

export async function deleteTeamFeishuWebhook(id: number): Promise<void> {
  await axios.delete(`/api/team/feishu/webhooks/${id}`)
}

export async function ensureTeamFeishuPreset(): Promise<TeamFeishuWebhook> {
  const res = await axios.post("/api/team/feishu/webhooks/ensure-preset")
  return res.data as TeamFeishuWebhook
}


export async function listTeamRequirements(): Promise<TeamRequirement[]> {
  const res = await axios.get("/api/team/requirements")
  return res.data as TeamRequirement[]
}

export async function createTeamRequirement(req: {
  project_id?: number | null
  source_team?: string
  title: string
  description?: string
  status?: "incoming" | "todo" | "in_progress" | "done" | "blocked"
  priority?: "low" | "medium" | "high" | "urgent"
  delivery?: { target_team_id: number } | null
}): Promise<TeamRequirement> {
  const res = await axios.post("/api/team/requirements", req)
  return res.data as TeamRequirement
}

export async function updateTeamRequirement(
  id: number,
  req: {
    project_id?: number | null
    source_team?: string
    title?: string
    description?: string
    status?: "incoming" | "todo" | "in_progress" | "done" | "blocked"
    priority?: "low" | "medium" | "high" | "urgent"
  },
): Promise<TeamRequirement> {
  const res = await axios.put(`/api/team/requirements/${id}`, req)
  return res.data as TeamRequirement
}

export async function deleteTeamRequirement(id: number): Promise<void> {
  await axios.delete(`/api/team/requirements/${id}`)
}

export async function acceptTeamRequirementDelivery(id: number): Promise<TeamRequirement> {
  const res = await axios.post(`/api/team/requirements/${id}/accept`)
  return res.data as TeamRequirement
}

export async function rejectTeamRequirementDelivery(id: number): Promise<{ ok: true }> {
  const res = await axios.post(`/api/team/requirements/${id}/reject`)
  return res.data as { ok: true }
}

export async function listTeamMembers(): Promise<TeamMember[]> {
  const res = await axios.get("/api/team/members")
  return res.data as TeamMember[]
}

export async function addTeamMember(req: {
  email: string
  name: string
  password?: string
  role?: "owner" | "admin" | "member"
}): Promise<TeamMember> {
  const res = await axios.post("/api/team/members", req)
  return res.data as TeamMember
}

export async function updateTeamMemberRole(userId: number, role: "owner" | "admin" | "member"): Promise<TeamMember> {
  const res = await axios.put(`/api/team/members/${userId}`, { role })
  return res.data as TeamMember
}

export async function removeTeamMember(userId: number): Promise<void> {
  await axios.delete(`/api/team/members/${userId}`)
}

export async function listTeamInvites(): Promise<TeamInvite[]> {
  const res = await axios.get("/api/team/invites")
  return res.data as TeamInvite[]
}

export async function createTeamInvite(req: {
  email?: string
  role?: "admin" | "member"
  expires_days?: number
}): Promise<TeamInvite> {
  const res = await axios.post("/api/team/invites", req)
  return res.data as TeamInvite
}

export async function deleteTeamInvite(inviteId: number): Promise<void> {
  await axios.delete(`/api/team/invites/${inviteId}`)
}
