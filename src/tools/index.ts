import type { ToolContext, ToolDefinition } from "./types.js"
import { createFsTools } from "./fs.js"
import { createShellTools } from "./shell.js"

export function createBuiltInTools(_ctx: ToolContext): ToolDefinition[] {
  return [...createFsTools(), ...createShellTools()]
}

