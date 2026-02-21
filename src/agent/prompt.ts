import fs from "node:fs/promises"
import path from "node:path"

async function readIfExists(filePath: string): Promise<string | null> {
  try {
    return await fs.readFile(filePath, "utf8")
  } catch {
    return null
  }
}

export async function loadRolePrompt(workspaceRoot: string, role: string): Promise<string> {
  const rolePath = path.join(workspaceRoot, "roles", `${role}.md`)
  const content = await readIfExists(rolePath)
  if (content) return content.trim()

  // fallback
  return `
你是“AI 员工”，目标是高质量完成用户交代的任务。
在不确定需求时先问 1-3 个澄清问题。
输出要简洁、可执行，必要时给出步骤和命令。
`.trim()
}

export async function loadSkillsPrompt(workspaceRoot: string): Promise<string> {
  const skillsDir = path.join(workspaceRoot, "skills")
  try {
    const entries = await fs.readdir(skillsDir, { withFileTypes: true })
    const files = entries.filter((e) => e.isFile() && e.name.toLowerCase().endsWith(".md"))
    if (files.length === 0) return ""
    const chunks: string[] = []
    for (const f of files.sort((a, b) => a.name.localeCompare(b.name))) {
      const p = path.join(skillsDir, f.name)
      const content = await fs.readFile(p, "utf8")
      chunks.push(`## skill:${f.name}\n${content.trim()}`)
    }
    return chunks.join("\n\n")
  } catch {
    return ""
  }
}

export async function buildSystemPrompt(workspaceRoot: string, role: string): Promise<string> {
  const rolePrompt = await loadRolePrompt(workspaceRoot, role)
  const skillsPrompt = await loadSkillsPrompt(workspaceRoot)

  const toolRules = `
### 工具使用规则
- 需要访问文件/目录时，用 fs_read / fs_list。
- 需要写文件时，用 fs_write（可能被禁用）。
- 需要运行命令时，用 shell_run（可能被禁用）。
- 工具参数必须是严格 JSON；不要臆造文件内容。
- 工具返回结果可能被截断，必要时分多次读取。
`.trim()

  return [rolePrompt, toolRules, skillsPrompt].filter(Boolean).join("\n\n")
}

