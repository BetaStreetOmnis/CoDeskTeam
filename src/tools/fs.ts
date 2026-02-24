import fs from "node:fs/promises"
import path from "node:path"
import { z } from "zod"
import { truncate } from "../util/text.js"
import { resolveWorkspacePath } from "../util/workspace-path.js"
import type { ToolDefinition } from "./types.js"

const SENSITIVE_ENV_FILENAMES = new Set([".env.example", ".env.sample", ".env.template"])

function isSensitiveResolvedPath(workspaceRoot: string, fullPath: string): boolean {
  const root = path.resolve(workspaceRoot)
  const rel = path.relative(root, fullPath)
  const parts = rel.split(path.sep).filter(Boolean).map((p) => p.toLowerCase())
  if (parts.includes(".aistaff") || parts.includes(".jetlinks-ai")) return true

  const base = path.basename(fullPath).toLowerCase()
  if (SENSITIVE_ENV_FILENAMES.has(base)) return false
  if (base === ".env" || base.startsWith(".env.")) return true
  return false
}

function assertNotSensitivePath(workspaceRoot: string, inputPath: string, fullPath: string) {
  if (isSensitiveResolvedPath(workspaceRoot, fullPath)) {
    throw new Error(`Access denied for sensitive path: ${inputPath}`)
  }
}

const FsReadInput = z.object({
  path: z.string().min(1),
})

const FsWriteInput = z.object({
  path: z.string().min(1),
  content: z.string(),
  mode: z.enum(["overwrite", "append"]).default("overwrite"),
})

const FsListInput = z.object({
  path: z.string().default("."),
  depth: z.number().int().min(0).max(5).default(2),
  maxEntries: z.number().int().min(1).max(5000).default(500),
})

async function listDirRecursive(
  dir: string,
  options: { depth: number; maxEntries: number },
  prefix = "",
): Promise<string[]> {
  if (options.maxEntries <= 0) return []
  const entries = await fs.readdir(dir, { withFileTypes: true })
  const lines: string[] = []
  for (const entry of entries) {
    if (lines.length >= options.maxEntries) break
    const marker = entry.isDirectory() ? "/" : ""
    lines.push(`${prefix}${entry.name}${marker}`)
    if (entry.isDirectory() && options.depth > 0) {
      const child = path.join(dir, entry.name)
      const childLines = await listDirRecursive(child, {
        depth: options.depth - 1,
        maxEntries: options.maxEntries - lines.length,
      }, `${prefix}${entry.name}/`)
      lines.push(...childLines)
    }
  }
  return lines
}

export function createFsTools(): ToolDefinition[] {
  const fs_read: ToolDefinition<typeof FsReadInput> = {
    name: "fs_read",
    description: "读取工作区内的文本文件",
    risk: "safe",
    parametersJsonSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        path: { type: "string", description: "相对工作区根目录的路径" },
      },
      required: ["path"],
    },
    inputSchema: FsReadInput,
    handler: async (input, ctx) => {
      const fullPath = resolveWorkspacePath(ctx.workspaceRoot, input.path)
      assertNotSensitivePath(ctx.workspaceRoot, input.path, fullPath)
      const content = await fs.readFile(fullPath, "utf8")
      return truncate(content, ctx.maxFileReadChars)
    },
  }

  const fs_write: ToolDefinition<typeof FsWriteInput> = {
    name: "fs_write",
    description: "写入工作区内的文本文件（默认禁用，需要显式开启）",
    risk: "dangerous",
    parametersJsonSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        path: { type: "string", description: "相对工作区根目录的路径" },
        content: { type: "string", description: "写入内容" },
        mode: { type: "string", enum: ["overwrite", "append"], default: "overwrite" },
      },
      required: ["path", "content"],
    },
    inputSchema: FsWriteInput,
    handler: async (input, ctx) => {
      if (!ctx.enableWrite) {
        throw new Error("fs_write is disabled. Set JETLINKS_AI_ENABLE_WRITE=1 to enable.")
      }
      const fullPath = resolveWorkspacePath(ctx.workspaceRoot, input.path)
      assertNotSensitivePath(ctx.workspaceRoot, input.path, fullPath)
      await fs.mkdir(path.dirname(fullPath), { recursive: true })
      if (input.mode === "append") await fs.appendFile(fullPath, input.content, "utf8")
      else await fs.writeFile(fullPath, input.content, "utf8")
      return { ok: true, path: input.path, mode: input.mode }
    },
  }

  const fs_list: ToolDefinition<typeof FsListInput> = {
    name: "fs_list",
    description: "列出工作区目录树（用于了解文件结构）",
    risk: "safe",
    parametersJsonSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        path: { type: "string", description: "相对工作区根目录的路径（默认 .）", default: "." },
        depth: { type: "integer", minimum: 0, maximum: 5, default: 2 },
        maxEntries: { type: "integer", minimum: 1, maximum: 5000, default: 500 },
      },
    },
    inputSchema: FsListInput,
    handler: async (input, ctx) => {
      const fullPath = resolveWorkspacePath(ctx.workspaceRoot, input.path)
      assertNotSensitivePath(ctx.workspaceRoot, input.path, fullPath)
      const lines = await listDirRecursive(fullPath, { depth: input.depth, maxEntries: input.maxEntries })
      return lines.join("\n")
    },
  }

  return [fs_read, fs_write, fs_list]
}
