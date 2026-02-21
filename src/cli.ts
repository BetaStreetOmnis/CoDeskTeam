#!/usr/bin/env node
import "dotenv/config"
import { Command } from "commander"
import process from "node:process"
import { createInterface } from "node:readline/promises"
import { loadConfig } from "./config.js"
import { buildSystemPrompt } from "./agent/prompt.js"
import { runAgentTask } from "./agent/run-task.js"
import type { ChatMessage } from "./agent/types.js"
import { createBuiltInTools } from "./tools/index.js"
import type { ToolContext } from "./tools/types.js"
import { OpenAiProvider } from "./llm/openai.js"
import { MockProvider } from "./llm/mock.js"
import type { ModelProvider } from "./llm/types.js"
import { startGateway } from "./gateway/server.js"
import { connectAndChat } from "./gateway/client.js"

function createProvider(config: ReturnType<typeof loadConfig>): ModelProvider {
  if (config.provider === "mock") return new MockProvider()
  if (!config.openaiApiKey) {
    throw new Error("Missing OPENAI_API_KEY. Set it in .env or environment variables.")
  }
  return new OpenAiProvider(config.openaiApiKey)
}

function createToolContext(config: ReturnType<typeof loadConfig>): ToolContext {
  return {
    workspaceRoot: config.workspaceRoot,
    enableShell: config.enableShell,
    enableWrite: config.enableWrite,
    maxFileReadChars: config.maxFileReadChars,
    maxToolOutputChars: config.maxToolOutputChars,
  }
}

async function runOnce(options: {
  task: string
  role: string
  configOverrides: Partial<ReturnType<typeof loadConfig>>
}) {
  const config = loadConfig(options.configOverrides)
  const provider = createProvider(config)
  const toolContext = createToolContext(config)
  const tools = createBuiltInTools(toolContext)
  const systemPrompt = await buildSystemPrompt(config.workspaceRoot, options.role)

  const messages: ChatMessage[] = [{ role: "system", content: systemPrompt }]
  const result = await runAgentTask({
    provider,
    model: config.model,
    messages,
    userInput: options.task,
    tools,
    toolContext,
    maxSteps: config.maxSteps,
    onEvent: (e) => {
      if (e.type === "tool_call") process.stdout.write(`(tool_call) ${e.toolName} ${JSON.stringify(e.args)}\n`)
      if (e.type === "tool_result") process.stdout.write(`(tool_result) ${e.toolName}\n`)
    },
  })

  process.stdout.write(result.finalText + "\n")
}

async function chatLocal(options: { role: string; configOverrides: Partial<ReturnType<typeof loadConfig>> }) {
  const config = loadConfig(options.configOverrides)
  const provider = createProvider(config)
  const toolContext = createToolContext(config)
  const tools = createBuiltInTools(toolContext)
  const systemPrompt = await buildSystemPrompt(config.workspaceRoot, options.role)

  let messages: ChatMessage[] = [{ role: "system", content: systemPrompt }]

  const rl = createInterface({ input: process.stdin, output: process.stdout })
  process.stdout.write("输入 :exit 退出\n")
  try {
    for (;;) {
      const line = await rl.question("> ")
      const trimmed = line.trim()
      if (!trimmed) continue
      if (trimmed === ":exit" || trimmed === ":quit") break

      const result = await runAgentTask({
        provider,
        model: config.model,
        messages,
        userInput: trimmed,
        tools,
        toolContext,
        maxSteps: config.maxSteps,
        onEvent: (e) => {
          if (e.type === "tool_call") process.stdout.write(`(tool_call) ${e.toolName} ${JSON.stringify(e.args)}\n`)
          if (e.type === "tool_result") process.stdout.write(`(tool_result) ${e.toolName}\n`)
        },
      })

      messages = result.messages
      process.stdout.write(result.finalText + "\n")
    }
  } finally {
    rl.close()
  }
}

async function main() {
  const program = new Command()

  program.name("aistaff").description("AI 员工（本地 Agent + 可选 Gateway）").version("0.1.0")

  const withCommonOptions = (cmd: Command) =>
    cmd
      .option("--provider <provider>", "openai | mock")
      .option("--model <model>", "模型名称")
      .option("--workspace <path>", "工作区根目录")
      .option("--enable-shell", "启用 shell_run（危险）")
      .option("--enable-write", "启用 fs_write（危险）")
      .option("--port <port>", "Gateway 端口", (v) => Number.parseInt(v, 10))
      .option("--max-steps <n>", "最大工具循环次数", (v) => Number.parseInt(v, 10))

  withCommonOptions(
    program
      .command("run")
      .argument("<task>", "要执行的任务")
      .option("--role <role>", "角色（对应 roles/<role>.md）", "general")
      .action(async (task, opts) => {
        await runOnce({
          task,
          role: opts.role,
          configOverrides: {
            provider: opts.provider,
            model: opts.model,
            workspaceRoot: opts.workspace,
            enableShell: opts.enableShell ? true : undefined,
            enableWrite: opts.enableWrite ? true : undefined,
            port: Number.isFinite(opts.port) ? opts.port : undefined,
            maxSteps: Number.isFinite(opts.maxSteps) ? opts.maxSteps : undefined,
          },
        })
      }),
  )

  withCommonOptions(
    program
      .command("chat")
      .option("--role <role>", "角色（对应 roles/<role>.md）", "general")
      .action(async (opts) => {
        await chatLocal({
          role: opts.role,
          configOverrides: {
            provider: opts.provider,
            model: opts.model,
            workspaceRoot: opts.workspace,
            enableShell: opts.enableShell ? true : undefined,
            enableWrite: opts.enableWrite ? true : undefined,
            port: Number.isFinite(opts.port) ? opts.port : undefined,
            maxSteps: Number.isFinite(opts.maxSteps) ? opts.maxSteps : undefined,
          },
        })
      }),
  )

  withCommonOptions(
    program
      .command("gateway")
      .option("--role <role>", "角色（对应 roles/<role>.md）", "general")
      .action(async (opts) => {
        const config = loadConfig({
          provider: opts.provider,
          model: opts.model,
          workspaceRoot: opts.workspace,
          enableShell: opts.enableShell ? true : undefined,
          enableWrite: opts.enableWrite ? true : undefined,
          port: Number.isFinite(opts.port) ? opts.port : undefined,
          maxSteps: Number.isFinite(opts.maxSteps) ? opts.maxSteps : undefined,
        })
        const provider = createProvider(config)

        await startGateway({ config, provider, role: opts.role })
        process.stdout.write(`Gateway listening on ws://127.0.0.1:${config.port}/ws\n`)
      }),
  )

  program
    .command("connect")
    .description("连接到已启动的 Gateway")
    .option("--url <wsUrl>", "WebSocket URL", undefined)
    .action(async (opts) => {
      const config = loadConfig()
      const url = opts.url ?? `ws://127.0.0.1:${config.port}/ws`
      await connectAndChat(url)
    })

  // Some runners (pnpm+tsx) may inject a leading "--" which breaks option parsing.
  const argv = process.argv.slice()
  if (argv[2] === "--") argv.splice(2, 1)
  await program.parseAsync(argv)
}

main().catch((e) => {
  process.stderr.write(String(e) + "\n")
  process.exitCode = 1
})
