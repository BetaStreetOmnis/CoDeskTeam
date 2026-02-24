import { z } from "zod"

export type AiStaffProvider = "openai" | "mock"

export type AiStaffConfig = {
  provider: AiStaffProvider
  model: string
  openaiApiKey?: string
  workspaceRoot: string
  enableShell: boolean
  enableWrite: boolean
  port: number
  maxSteps: number
  maxToolOutputChars: number
  maxFileReadChars: number
}

const EnvSchema = z
  .object({
    JETLINKS_AI_PROVIDER: z.enum(["openai", "mock"]).optional(),
    AISTAFF_PROVIDER: z.enum(["openai", "mock"]).optional(),
    JETLINKS_AI_MODEL: z.string().optional(),
    AISTAFF_MODEL: z.string().optional(),
    OPENAI_API_KEY: z.string().optional(),
    JETLINKS_AI_WORKSPACE: z.string().optional(),
    AISTAFF_WORKSPACE: z.string().optional(),
    JETLINKS_AI_ENABLE_SHELL: z.string().optional(),
    AISTAFF_ENABLE_SHELL: z.string().optional(),
    JETLINKS_AI_ENABLE_WRITE: z.string().optional(),
    AISTAFF_ENABLE_WRITE: z.string().optional(),
    JETLINKS_AI_PORT: z.string().optional(),
    AISTAFF_PORT: z.string().optional(),
    JETLINKS_AI_MAX_STEPS: z.string().optional(),
    AISTAFF_MAX_STEPS: z.string().optional(),
    JETLINKS_AI_MAX_TOOL_OUTPUT_CHARS: z.string().optional(),
    AISTAFF_MAX_TOOL_OUTPUT_CHARS: z.string().optional(),
    JETLINKS_AI_MAX_FILE_READ_CHARS: z.string().optional(),
    AISTAFF_MAX_FILE_READ_CHARS: z.string().optional(),
  })
  .passthrough()

function parseBool(value: string | undefined, defaultValue: boolean): boolean {
  if (value === undefined) return defaultValue
  const normalized = value.trim().toLowerCase()
  if (["1", "true", "yes", "y", "on"].includes(normalized)) return true
  if (["0", "false", "no", "n", "off"].includes(normalized)) return false
  return defaultValue
}

function parseIntWithDefault(value: string | undefined, defaultValue: number): number {
  if (value === undefined) return defaultValue
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? parsed : defaultValue
}

export function loadConfig(overrides: Partial<AiStaffConfig> = {}): AiStaffConfig {
  const env = EnvSchema.parse(process.env)

  const provider = overrides.provider ?? env.JETLINKS_AI_PROVIDER ?? env.AISTAFF_PROVIDER ?? "openai"
  const model = overrides.model ?? env.JETLINKS_AI_MODEL ?? env.AISTAFF_MODEL ?? "gpt-5.2"
  const openaiApiKey = overrides.openaiApiKey ?? env.OPENAI_API_KEY
  const workspaceRoot = overrides.workspaceRoot ?? env.JETLINKS_AI_WORKSPACE ?? env.AISTAFF_WORKSPACE ?? process.cwd()
  const enableShell =
    overrides.enableShell ?? parseBool(env.JETLINKS_AI_ENABLE_SHELL ?? env.AISTAFF_ENABLE_SHELL, /* default */ false)
  const enableWrite =
    overrides.enableWrite ?? parseBool(env.JETLINKS_AI_ENABLE_WRITE ?? env.AISTAFF_ENABLE_WRITE, /* default */ false)
  const port = overrides.port ?? parseIntWithDefault(env.JETLINKS_AI_PORT ?? env.AISTAFF_PORT, 18790)
  const maxSteps = overrides.maxSteps ?? parseIntWithDefault(env.JETLINKS_AI_MAX_STEPS ?? env.AISTAFF_MAX_STEPS, 10)
  const maxToolOutputChars =
    overrides.maxToolOutputChars ?? parseIntWithDefault(env.JETLINKS_AI_MAX_TOOL_OUTPUT_CHARS ?? env.AISTAFF_MAX_TOOL_OUTPUT_CHARS, 12_000)
  const maxFileReadChars =
    overrides.maxFileReadChars ?? parseIntWithDefault(env.JETLINKS_AI_MAX_FILE_READ_CHARS ?? env.AISTAFF_MAX_FILE_READ_CHARS, 120_000)

  return {
    provider,
    model,
    openaiApiKey,
    workspaceRoot,
    enableShell,
    enableWrite,
    port,
    maxSteps,
    maxToolOutputChars,
    maxFileReadChars,
  }
}
