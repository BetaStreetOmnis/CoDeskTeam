import path from "node:path"

export function resolveWorkspacePath(workspaceRoot: string, inputPath: string): string {
  const root = path.resolve(workspaceRoot)
  const resolved = path.resolve(root, inputPath)
  if (resolved === root) return resolved
  if (resolved.startsWith(root + path.sep)) return resolved
  throw new Error(`Path escapes workspace root: ${inputPath}`)
}

