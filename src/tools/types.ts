import { z } from "zod"

export type ToolRisk = "safe" | "dangerous"

export type ToolContext = {
  workspaceRoot: string
  enableShell: boolean
  enableWrite: boolean
  maxFileReadChars: number
  maxToolOutputChars: number
}

export type ToolDefinition<InputSchema extends z.ZodTypeAny = z.ZodTypeAny> = {
  name: string
  description: string
  risk: ToolRisk
  parametersJsonSchema: Record<string, unknown>
  inputSchema: InputSchema
  handler: (input: z.output<InputSchema>, ctx: ToolContext) => Promise<unknown>
}

