import { z } from "zod"
import { runCommand } from "../util/run-command.js"
import type { ToolDefinition } from "./types.js"

const ShellRunInput = z.object({
  command: z.string().min(1),
  timeoutMs: z.number().int().min(0).max(10 * 60 * 1000).default(60_000),
})

export function createShellTools(): ToolDefinition[] {
  const shell_run: ToolDefinition<typeof ShellRunInput> = {
    name: "shell_run",
    description: "在工作区根目录执行 shell 命令（默认禁用，需要显式开启）",
    risk: "dangerous",
    parametersJsonSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        command: { type: "string", description: "要执行的命令" },
        timeoutMs: { type: "integer", minimum: 0, maximum: 600000, default: 60000 },
      },
      required: ["command"],
    },
    inputSchema: ShellRunInput,
    handler: async (input, ctx) => {
      if (!ctx.enableShell) {
        throw new Error("shell_run is disabled. Set JETLINKS_AI_ENABLE_SHELL=1 to enable.")
      }
      const result = await runCommand(input.command, {
        cwd: ctx.workspaceRoot,
        timeoutMs: input.timeoutMs,
        maxOutputChars: ctx.maxToolOutputChars,
      })
      return result
    },
  }

  return [shell_run]
}
