export { health, setAuthToken } from "./client"

export {
  authLogin,
  authRegister,
  authSetup,
  authStatus,
  listAuthTeams,
  getMe,
  switchTeam,
} from "./auth"
export type {
  AuthResponse,
  AuthStatusResponse,
  LoginRequest,
  MeResponse,
  PublicTeam,
  SetupRequest,
} from "./auth"

export { chat } from "./chat"
export type { ChatAttachment, ChatEvent, ChatRequest, ChatResponse, ChatSecurityPreset } from "./chat"

export { uploadFile, uploadImage, getFilePreview } from "./files"
export type { UploadFileResponse, UploadImageResponse, FilePreviewResponse } from "./files"

export {
  deleteHistorySession,
  getHistorySession,
  listHistoryFiles,
  listHistorySessions,
  searchHistory,
} from "./history"
export type {
  HistoryAttachment,
  HistoryFileItem,
  HistoryMessageItem,
  HistorySearchHit,
  HistorySessionDetailResponse,
  HistorySessionItem,
} from "./history"

export { createPpt, createQuote, createQuoteXlsx } from "./docs"
export type { PptRequest, QuoteRequest } from "./docs"

export { generatePrototype } from "./prototype"
export type { PrototypeRequest } from "./prototype"

export { browserNavigate, browserScreenshot, browserStart } from "./browser"

export {
  chatbiChat,
  chatbiChatStream,
  chatbiRunSql,
  deleteChatbiDatasource,
  listChatbiDatasources,
  upsertChatbiDatasource,
} from "./chatbi"
export type {
  ChatbiChatRequest,
  ChatbiChatResponse,
  ChatbiDatasource,
  ChatbiStreamEvent,
  ChatbiUpsertDatasourceRequest,
} from "./chatbi"

export { listSkills, runSkill } from "./skills"
export type { BuiltinSkill } from "./skills"

export {
  addTeamMember,
  aiDraftTeamSkill,
  acceptTeamRequirementDelivery,
  createTeamFeishuWebhook,
  createTeamInvite,
  createTeamProject,
  createTeamRequirement,
  createTeamSkill,
  discoverTeamProjects,
  deleteTeamFeishuWebhook,
  deleteTeamInvite,
  deleteTeamProject,
  deleteTeamRequirement,
  deleteTeamSkill,
  ensureTeamFeishuPreset,
  getTeamSettings,
  getTeamProjectTree,
  getTeamWorkspaceTree,
  getTeamProjectReadme,
  getTeamWorkspaceReadme,
  importTeamProjects,
  listTeamFeishuWebhooks,
  listTeamInvites,
  listTeamMembers,
  listTeamProjects,
  listTeamRequirements,
  listTeamSkills,
  rejectTeamRequirementDelivery,
  removeTeamMember,
  updateTeamFeishuWebhook,
  updateTeamMemberRole,
  updateTeamProject,
  updateTeamRequirement,
  updateTeamSettings,
  updateTeamSkill,
  exportTeamDbMarkdown,
} from "./team"
export type {
  TeamDbExport,
  TeamFeishuWebhook,
  TeamInvite,
  TeamMember,
  TeamProjectCandidate,
  TeamProjectImportResult,
  TeamProjectImportSkipped,
  TeamProject,
  TeamProjectTreeNode,
  TeamProjectReadme,
  TeamRequirementDelivery,
  TeamRequirement,
  TeamSettings,
  TeamSkill,
  TeamSkillAIDraftRequest,
  TeamSkillAIDraftResponse,
} from "./team"
