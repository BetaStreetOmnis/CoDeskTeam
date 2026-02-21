import { spawn } from "node:child_process"

export type RunCommandResult = {
  exitCode: number | null
  signal: NodeJS.Signals | null
  stdout: string
  stderr: string
  durationMs: number
  timedOut: boolean
}

export async function runCommand(
  command: string,
  options: { cwd: string; timeoutMs: number; maxOutputChars: number },
): Promise<RunCommandResult> {
  const startedAt = Date.now()
  const child = spawn(command, {
    cwd: options.cwd,
    shell: true,
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
  })

  let stdout = ""
  let stderr = ""

  const append = (target: "stdout" | "stderr", chunk: Buffer) => {
    const text = chunk.toString("utf8")
    if (target === "stdout") stdout += text
    else stderr += text

    const total = stdout.length + stderr.length
    if (total > options.maxOutputChars) {
      child.kill("SIGKILL")
    }
  }

  child.stdout?.on("data", (c) => append("stdout", c))
  child.stderr?.on("data", (c) => append("stderr", c))

  let timeoutHandle: NodeJS.Timeout | undefined
  let timedOut = false
  if (options.timeoutMs > 0) {
    timeoutHandle = setTimeout(() => {
      timedOut = true
      child.kill("SIGKILL")
    }, options.timeoutMs)
  }

  const result = await new Promise<Omit<RunCommandResult, "durationMs" | "timedOut">>((resolve) => {
    child.on("close", (exitCode, signal) => {
      resolve({ exitCode, signal, stdout, stderr })
    })
  })

  if (timeoutHandle) clearTimeout(timeoutHandle)

  return {
    ...result,
    timedOut,
    durationMs: Date.now() - startedAt,
  }
}

