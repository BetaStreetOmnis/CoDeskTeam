# JetLinks AI · 企业版 OpenClaw 工作台

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

JetLinks AI 是一个开源、可自托管的 **团队 AI 交付工作台**。  
你可以把它理解为 **更适合企业和团队落地的 OpenClaw 工作台**：把对话式执行、共享上下文、需求/项目管理、交付物生成，以及 OpenClaw 运营能力整合到一个产品里。

> 从“想法 / 需求”到“执行 / 交付”，把聊天、项目、文档、原型和 OpenClaw 运营统一到一个界面里。

> 鸣谢：本项目在网关/多渠道接入思路上参考了 OpenClaw，并提供可选的 OpenClaw ingress 集成入口。  

## 为什么更适合团队落地

- **不只是聊天窗口**：把 AI 对话、团队技能、需求流转和项目协同放进同一个工作台
- **天然面向交付**：可直接生成 PPT、报价单、报检单、原型和海报等结果物
- **OpenClaw 更易运营**：内置网关状态、资源同步、频道/插件/技能管理与团队级资源视图
- **自托管可控**：基于 FastAPI + Vue，支持 SQLite / Postgres，默认安全收敛
- **企业体验更完整**：支持多团队、权限治理、工作区隔离，以及小屏/移动端适配

## 核心亮点

- **团队优先工作台**：用户、团队、邀请、角色权限、项目/工作区切换
- **AI 工作台**：聊天、历史、上传下载、内置技能、团队 Prompt 技能、共享上下文
- **交付物生成**：PPT、报价单、报检单、HTML 原型、SVG 海报/长图
- **AI+ Pipeline**：视觉、媒体、内容、办公、全链路编排
- **OpenClaw 运营中心**：状态探测、一键同步、频道/插件/技能管理、团队级技能注册表
- **默认更安全**：`shell`、`write`、`browser` 等高风险工具需显式开启

## 预览

![JetLinks AI · 企业版 OpenClaw 工作台](docs/images/github-hero.svg)

![JetLinks AI 界面截图](docs/images/screenshot.png)

### 更多界面截图

| 初始化与首次进入 | 工作区与 README 预览 |
| --- | --- |
| ![初始化页面](docs/images/screenshot-setup.png) | ![工作区页面](docs/images/screenshot-workspace.png) |

| 内置技能模板中心 | AI 对话主界面 |
| --- | --- |
| ![技能中心](docs/images/screenshot-skills.png) | ![对话界面](docs/images/screenshot-chat.png) |

| 智能问数（ChatBI） |
| --- |
| ![智能问数页面](docs/images/screenshot-chatbi.png) |

## 平台功能总览

| 模块 | 能做什么 | 主要接口 / 代码模块 |
| --- | --- | --- |
| 身份与多团队 | 初始化管理员、登录注册、切换团队、管理邀请和成员 | `/api/auth/*`、`/api/team/invites`、`/api/team/members` |
| 项目与工作区 | 注册仓库、发现/导入项目、浏览目录树、预览 README、导出 Markdown | `/api/team/projects*`、`/api/team/workspace/*`、`/api/team/export-md` |
| 需求协同 | 创建需求、分派交付团队、处理接单/拒单 | `/api/team/requirements*` |
| AI 对话与 Agent | 带附件聊天、选择 provider、按安全预设运行工具，并复用团队上下文 | `/api/chat`、`AgentService`、`agent/tools/*` |
| 技能中心 | 使用内置 Pipeline，维护团队 Prompt 技能，并支持 AI 草拟技能 | `/api/skills`、`/api/skills/pipeline/*`、`/api/team/skills*` |
| 交付物中心 | 生成 PPT、报价单、报检单、海报、HTML 原型，并支持预览/下载 | `/api/docs/*`、`/api/prototype/*`、`/api/files/*` |
| 历史与检索 | 查看会话/文件历史、恢复上下文、检索工作区与历史快照 | `/api/history/*` |
| ChatBI | 管理数据源，自然语言问数，流式返回 SQL、结果和分析 | `/api/chatbi/*` |
| 浏览器与受控工具 | 启动浏览器、导航、截图，并通过 `.env` 控制 shell/write/browser 权限 | `/api/browser/*`、工具开关 |
| OpenClaw 与外部通道 | 查看网关状态、同步频道/插件/技能，并接收 OpenClaw / 飞书 / 企微事件 | `/api/team/openclaw/*`、`/api/integrations/openclaw/message`、`/api/feishu/*`、`/api/wecom/*` |

## 提供商、档案与安全档位

### 提供商矩阵

提供商列表不是写死的。前端会读取 `/api/meta`，最终可选项取决于你的本地运行环境、`.env` 配置和已安装的 CLI。

| 提供商 | 适合场景 | 说明 |
| --- | --- | --- |
| `openai` | 通用对话、文档、PPT、报价、原型 | 内置完整工具链，最适合交付物生成 |
| `glm` | 备用大模型通道 | 配置 `GLM_API_KEY` 后出现 |
| `codex` | 本地代码任务、仓库改造 | 依赖本地 Codex CLI，可选无沙箱模式 |
| `claude` | 本地 Claude CLI 工作流 | 仅在配置的 Claude 命令可用时出现 |
| `opencode` | 带审批链路的 Agent 工程流 | 适合工程任务；文档/原型场景可自动回退内置工具链 |
| `nanobot` | 外部编码/任务代理 | 适合委托执行；文档/原型可回退内置工具链 |
| `openclaw` | OpenClaw 接入运行时 | 开启 OpenClaw 集成后可用 |
| `pi` | Pi 编码代理 | 需设置 `JETLINKS_AI_ENABLE_PI=1` |
| `mock` | 演示、测试、截图 | 安全的假模型，返回稳定演示结果 |

### 内置 Agent 档案

工作台支持一键套用 “provider + 角色 + 风格 + 安全档位” 组合：

| 档案 | 默认 provider | 角色 | 安全档位 | 适用场景 |
| --- | --- | --- | --- | --- |
| 默认助理 | `opencode` | `general` | `safe` | 日常协作、轻量任务 |
| 工程模式 | `opencode` | `engineer` | `power` | 改代码、跑工具、工程交付 |
| 文档模式 | `openai` | `general` | `standard` | PPT、报价单、文档生成 |
| 原型模式 | `openai` | `engineer` | `standard` | HTML 页面与原型产物 |
| 研究模式 | `openai` | `general` | `safe` | 信息整理、低权限分析 |
| 自定义 | 当前手动选择 | 手动 | 手动 | 按单次会话精细配置 |

### 安全档位

前端档位只是在服务端允许范围内“申请能力”；真正的上限仍由 `.env` 控制。

| 档位 | Shell | Write | Browser | 适合什么 |
| --- | --- | --- | --- | --- |
| `safe` | 关 | 关 | 关 | 只读问答、信息整理 |
| `standard` | 关 | 开 | 关 | 文档生成、文件产出 |
| `power` | 开 | 开 | 开 | 管理员/工程场景的全能力模式 |
| `custom` | 手动 | 手动 | 手动 | 精细控制每一项能力 |

### 推荐怎么选 provider

| 如果你想… | 推荐 provider | 原因 |
| --- | --- | --- |
| 稳定生成 PPT、报价单、海报、报检单、原型 | `openai` | 直接走内置文档/原型工具链，交付能力最完整 |
| 在本地仓库里改代码、做工程任务 | `codex` | 更适合本地代码修改和仓库级工程工作流 |
| 跑带审批风格的工程 Agent 流程 | `opencode` | 更贴合带审批/受控执行的工程协作流程 |
| 使用国产/替代模型通道 | `glm` | 适合已经统一到 GLM 体系的部署环境 |
| 把任务接到 OpenClaw 运行时里 | `openclaw` | 适合已经围绕 OpenClaw 做运营和资源管理的团队 |
| 做演示、截图、无成本试用界面 | `mock` | 不依赖真实模型和密钥，适合本地演示与冒烟测试 |

实用建议：

- 做交付物、通用聊天，优先用 `openai`
- 明确是“改这个仓库里的代码”，优先用 `codex`
- 需要审批式工程流或外部 Agent 协作，优先用 `opencode`
- 做演示、培训、README 截图，优先用 `mock`
- 只有在基础设施、合规要求或现有工作流明确需要时，再切换到其他 provider

## 工作台导航说明

### 左侧主分区

| 分区 | 内容 |
| --- | --- |
| 工作台 | 项目、需求、能力开关、AI+ 工具集、浏览器、ChatBI |
| 技能 | 内置技能模板 + 团队 Prompt 技能 |
| 历史 | 会话历史、产物文件、目录检索 |
| 运行 | 当前会话运行轨迹、上下文与执行状态 |

### 工作台页签

| 页签 | 作用 |
| --- | --- |
| 项目维护 | 项目注册、目录树、README 预览、项目导入/发现 |
| 需求维护 | 需求看板、跨团队交付、接单/拒单流转 |
| 能力开关 | provider/档案选择、安全档位、shell/write/browser 开关 |
| AI+工具集 | 视觉、媒体、内容、办公等 Pipeline 式能力 |
| 智能问数 | 对本地或远程数据源进行自然语言问数 |
| 浏览器 | 内置浏览器会话、页面跳转和截图 |

## 服务拓扑图

```mermaid
flowchart TD
  User[团队成员 / 管理员] --> Web[Vue 工作台]
  Web --> Auth[认证与团队隔离]
  Web --> Workspace[项目 / 需求 / 技能]
  Web --> Chat[AI 对话控制台]
  Web --> History[历史 / 文件 / 检索]
  Web --> ChatBI[ChatBI 分析]
  Web --> Ops[OpenClaw 运营中心]

  Chat --> Agent[AgentService]
  Agent --> Providers[OpenAI / Codex / OpenCode / Pi / Nanobot / Claude]
  Agent --> Tools[Shell / Write / Browser / Docs / Prototype / Attachments]

  Workspace --> Export[README 预览 / Markdown 导出]
  Tools --> Deliverables[PPT / 报价 / 报检 / 海报 / 原型]
  ChatBI --> DataSources[SQLite / 远程数据源]
  Ops --> Gateway[OpenClaw 网关资源]

  Auth --> DB[(SQLite / Postgres)]
  History --> DB
  Export --> Files[(outputs/ + file_records)]
  Deliverables --> Files
```

## 主要服务模块

- **`AuthService`**：管理员初始化、登录注册、团队切换与权限控制
- **`AgentService`**：provider 路由、工具编排、会话回灌、事件追踪
- **`DocService` + `services/docs/*`**：PPT、报价单、报检单、海报生成
- **`PrototypeService`**：HTML 原型打包与在线预览
- **`QueryEngine` + `services/chatbi/*`**：ChatBI 数据源管理、SQL 生成、执行与分析
- **`OpenClawAdminService`**：OpenClaw 状态探测、资源同步、团队级配置管理
- **`FeishuWebhookService` / `WecomService`**：飞书、企微回调接入与团队集成
- **`TeamExportService` / `history_file_store`**：工作区导出、文件索引、历史检索

本仓库包含完整前后端代码，适合自托管部署或二次开发扩展。

## 快速开始

### 0) 环境依赖

- Node.js `>= 22` + `pnpm`
- Python `>= 3.10` + `uv`（后端依赖管理）

可选：

- LibreOffice（用于 PPT 封面预览图生成；没有也能生成 PPTX）
- Playwright（用于浏览器工具；默认关闭）

### 1) 启动（推荐）

```bash
pnpm dev
# 或
bash scripts/dev.sh
```

默认地址：

- Web: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/health`

首次启动需要在网页端完成 `setup` 初始化（创建第一个管理员账号与团队）。

### 2) 配置（最小必需）

```bash
cp .env.example .env
```

然后至少填写 `.env` 里的 `OPENAI_API_KEY`（如果你要使用对话/Agent 能力）。

### 2.5) Docker 部署（自托管）

仓库内置了一个开箱即用的 Docker Compose（默认单容器 + SQLite）：

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

默认地址：`http://127.0.0.1:8001`（UI + API），健康检查：`http://127.0.0.1:8001/health`。  
更多说明见：`docker/README.md`。

### 3) 数据库（SQLite / Postgres）

- 默认使用 SQLite（无需额外配置）。
- 生产建议使用 Postgres：设置 `JETLINKS_AI_DB_URL=postgresql://...`
- Postgres 迁移使用 Alembic：

```bash
cd backend
uv run alembic upgrade head
```

更详细的后端说明见 `backend/README.md`。

## 1. 架构总览

```mermaid
flowchart LR
  UI[frontend App.vue] --> API[FastAPI Routers]
  API --> Auth[Auth + Team ACL]
  API --> Agent[AgentService]
  API --> Data[(SQLite/Postgres)]
  API --> OutDir[JETLINKS_AI_OUTPUTS_DIR]

  Agent --> Session[SessionStore<br/>in-memory]
  Agent --> Loop[run_agent_task]
  Agent --> ProviderOpenAI[OpenAI Provider]
  Agent --> ProviderOpenCode[OpenCode Service]
  Agent --> ProviderNanobot[Nanobot Service]
  Loop --> Tools[Tool Layer]
  Tools --> FS[fs_list/fs_read/fs_write]
  Tools --> Shell[shell_run]
  Tools --> Browser[browser_*]
  Tools --> Doc[doc_*]
  Tools --> Proto[proto_generate]
  Tools --> Attach[attachment_read]

  Doc --> OutDir
  Proto --> OutDir
  Browser --> OutDir
  API --> HistorySnap[history_sessions/*.json]
  Data --> HistorySnap
```

## 2. 设计思路

### 2.1 分层职责

- Router 层：参数校验、鉴权、HTTP 响应拼装，尽量“薄”
- Service 层：业务编排（Agent、文档、浏览器、IM 回调）
- Agent 层：模型调用协议、工具循环、上下文裁剪、事件追踪
- Storage 层：SQLite/Postgres 持久化 + 内存会话 + 文件输出目录

### 2.2 会话与上下文

- 会话主键：`session_id`
- 双层存储：
  - 进程内：`SessionStore`（低延迟、含 TTL 和最大会话数裁剪）
  - 持久化：`chat_sessions` + `chat_messages`（可恢复）
- 重启恢复：`/api/chat` 会尝试把数据库历史回灌到内存会话
- 上下文控制：
  - `JETLINKS_AI_MAX_SESSION_MESSAGES`：限制历史消息条数
  - `JETLINKS_AI_MAX_CONTEXT_CHARS`：按字符估算做近似裁剪

### 2.3 Provider 策略

- `openai`：走内置 `run_agent_task + tools` 全能力链路
- `codex`：走本机 `codex exec --json` 非交互链路（适合代码任务）
- `pi`：走 `pi-mono` 的 Coding Agent CLI（文本模式；需要 `JETLINKS_AI_ENABLE_PI=1` + 子模块），适合代码/任务分解；对文档/PPT/原型/附件等场景会自动回退到内置 OpenAI 工具链
- `opencode` / `nanobot`：优先委托外部 Agent
- 对文档/PPT/原型/附件等场景，`opencode` 与 `nanobot` 会自动回退到内置 OpenAI 工具链，以保证产物能力一致
- provider 选择优先级：请求参数 `provider` > `.env` 中 `JETLINKS_AI_PROVIDER` > 后端默认 `openai`

### 2.3.1 OpenClaw / OpenCode（可选集成）

- 本仓库包含三个可选上游子模块：
  - `third_party/openclaw`：Moltbot/Clawdbot（网关 + 多渠道消息能力）
  - `third_party/opencode`：OpenCode（Agent loop + approvals）
  - `third_party/pi-mono`：Pi（Agent SDK + Coding Agent）
- 拉取子模块：`git submodule update --init --recursive`
- OpenClaw 网关入口（HTTP）：
  1) 团队 `owner/admin` 生成 token：`POST /api/team/integrations/openclaw`
  2) 网关发消息：`POST /api/integrations/openclaw/message`（Header: `x-jetlinks-ai-integration-token`）

### 2.4 安全策略

- 服务端开关是能力上限：`JETLINKS_AI_ENABLE_SHELL/WRITE/BROWSER`
- 前端只能在上限内“申请”能力，不能越权开启
- 高危能力仅团队 `owner/admin` 可启用
- 文件下载采用 JWT 下载令牌，不暴露裸文件路径
- Team/User 维度强隔离：会话、文件、技能、配置都绑定团队

### 2.5 可追溯与调试

- 聊天返回 `events`（工具调用、工具结果、裁剪、provider 事件）
- 历史会话可查看完整消息与事件
- 历史快照同步到 `.jetlinks-ai/history_sessions/`，支持目录检索（`/api/history/search`）

## 3. 核心链路

### 3.1 聊天链路（`POST /api/chat`）

1. 鉴权，解析团队与项目上下文
2. 组装团队技能提示词（`team_skills`）
3. 尝试会话回灌（数据库 -> `SessionStore`）
4. 调用 `AgentService.chat(...)`
5. Agent 根据 provider 走对应执行路径
6. 生成回复与事件
7. 持久化 `chat_sessions/chat_messages/file_records`
8. 同步历史快照（best effort）

### 3.2 工具执行链路

1. 模型输出 tool_calls
2. `run_agent_task` 逐个校验参数（Pydantic）
3. 调用 tool handler
4. 工具结果写回 `tool` 消息并进入下一轮
5. 直到模型给出最终 assistant 文本或达到 `max_steps`

### 3.3 文档/原型产物链路

1. 调用 `DocService` / `PrototypeService`
2. 输出文件写入 `JETLINKS_AI_OUTPUTS_DIR`（默认 `.jetlinks-ai/outputs`）
3. 生成带 token 的 `download_url`
4. 建立 `file_records` 索引，支持历史检索与下载

## 4. 代码结构（按职责）

### 4.1 后端

- `backend/jetlinks_ai_api/main.py`：应用入口、路由挂载、生命周期
- `backend/jetlinks_ai_api/config.py`：环境变量与配置加载
- `backend/jetlinks_ai_api/deps.py`：依赖注入、鉴权上下文
- `backend/jetlinks_ai_api/db.py`：SQLite/Postgres schema 与访问辅助
- `backend/jetlinks_ai_api/routers/`：HTTP API
- `backend/jetlinks_ai_api/services/`：业务服务
- `backend/jetlinks_ai_api/agent/`：Agent 运行时、provider、tools
- `backend/jetlinks_ai_api/session_store.py`：会话内存存储

### 4.2 前端

- `frontend/src/App.vue`：主界面与主要交互编排
- `frontend/src/composables/useTeamWorkspaceState.ts`：团队/项目/技能/需求状态
- `frontend/src/composables/useHistoryState.ts`：会话与文件历史状态
- `frontend/src/api/*.ts`：API 客户端分模块封装

### 4.3 其他

- `roles/`：角色系统提示词模板
- `skills/`：技能模板
- `JETLINKS_AI_OUTPUTS_DIR`：生成产物目录（默认 `.jetlinks-ai/outputs`）
- `.jetlinks-ai/`：运行期数据（DB、日志、JWT secret、历史快照）
- `src/` + `dist/`：旧版 Node CLI/Gateway 原型（兼容保留）

## 5. 数据模型（SQLite/Postgres）

核心表：

- 身份与团队：`users` `teams` `memberships` `invites`
- 团队配置：`team_skills` `team_projects` `team_requirements` `team_settings`
- IM 集成：`wecom_apps` `feishu_webhooks`
- 聊天与文件：`chat_sessions` `chat_messages` `file_records`
- 元数据：`meta`（schema version）

关系特征：

- 几乎所有业务数据都带 `team_id`，实现多团队隔离
- `chat_messages.session_id -> chat_sessions.session_id` 级联删除
- `file_records` 可关联 `project_id` 与 `session_id`，用于历史面板聚合

## 6. API 分组

认证与身份：

- `GET /api/auth/status`
- `POST /api/auth/setup`
- `POST /api/auth/login`
- `POST /api/auth/register`
- `GET /api/me`
- `POST /api/auth/switch-team`

聊天与历史：

- `POST /api/chat`
- `GET /api/history/sessions`
- `GET /api/history/sessions/{session_id}`
- `DELETE /api/history/sessions/{session_id}`
- `GET /api/history/files`
- `GET /api/history/search`

文件与产物：

- `POST /api/files/upload-image`
- `POST /api/files/upload-file`
- `GET /api/files/{file_id}`

文档与原型：

- `POST /api/docs/ppt`
  - 支持可选参数：`style`（`auto|modern_blue|minimal_gray|dark_tech|warm_business|template_jetlinks|template_team`）
  - 支持可选参数：`layout_mode`（`auto|focus|single_column|two_column|cards`）
- `POST /api/docs/quote`
- `POST /api/docs/quote-xlsx`
- `POST /api/docs/inspection`
- `POST /api/docs/inspection-xlsx`
- `POST /api/prototype/generate`
- `GET /api/prototype/preview/{prototype_id}/{file_path:path}`

工具/能力：

- `POST /api/browser/start`
- `POST /api/browser/navigate`
- `POST /api/browser/screenshot`
- `GET /api/skills`

团队后台：

- `GET/PUT /api/team/settings`
- `GET/POST/PUT/DELETE /api/team/projects`
- `GET /api/team/projects/discover`
- `POST /api/team/projects/import`
- `GET /api/team/projects/{project_id}/tree`
- `GET/POST/PUT/DELETE /api/team/skills`
- `POST /api/team/skills/ai-draft`
- `GET/POST/PUT/DELETE /api/team/requirements`
- `POST /api/team/requirements/{requirement_id}/accept`
- `POST /api/team/requirements/{requirement_id}/reject`
- `GET/POST/PUT/DELETE /api/team/members`
- `GET/POST/DELETE /api/team/invites`
- `GET/POST/PUT/DELETE /api/team/wecom/apps`
- `GET/POST/PUT/DELETE /api/team/feishu/webhooks`
- `POST /api/team/feishu/webhooks/ensure-preset`

OpenAI 兼容代理：

- `POST /openai/v1/responses`
- `POST /openai/v1/chat/completions`
- `GET /openai/v1/models`

### 6.1 需求交付（跨团队）

需求页仍使用现有的 `team_requirements`（`incoming/todo/in_progress/done/blocked`），只是在**创建需求**时可选带上结构化的交付信息 `delivery`，用于把需求“交付”到其它团队处理：

- 发起交付：源团队 `owner/admin` 在创建需求时传 `delivery.target_team_id`
  - 系统会把这条需求**直接创建到目标团队**（`team_id=target_team_id`）
  - 并强制设置：`status=incoming`、`source_team=源团队名称`、`delivery_state=pending`
- 接收/拒绝：目标团队 `owner/admin` 处理
  - 接收：`POST /api/team/requirements/{requirement_id}/accept`（`delivery_state=accepted`；若 `status=incoming` 会自动推进到 `todo`）
  - 拒绝：`POST /api/team/requirements/{requirement_id}/reject`（`delivery_state=rejected`；默认列表会过滤掉被拒绝的交付）

说明：交付需求当前是“单条记录”模式——只在目标团队侧存在一条需求记录（源团队列表不会自动生成镜像）。

### 6.2 报价单生成示例（XLSX / DOCX）

说明：

- 报价单接口需要登录（`Authorization: Bearer <access_token>`）
- 返回的 `download_url` 默认是**相对路径**（如 `/api/files/...`）；如果你配置了 `JETLINKS_AI_PUBLIC_BASE_URL`，则会返回绝对 URL

#### 1) 登录获取 token

```bash
API=http://127.0.0.1:8000

TOKEN=$(
  curl -sS -X POST "$API/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d '{"email":"admin@example.com","password":"your-password"}' \
  | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])'
)
```

#### 2) 生成 Excel 报价单（推荐）

```bash
META=$(
  curl -sS -X POST "$API/api/docs/quote-xlsx" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{
      "seller": "某某科技有限公司",
      "buyer": "某某客户有限公司",
      "currency": "CNY",
      "items": [
        { "name": "AI 工作台私有化部署", "quantity": 1,  "unit_price": 68000, "unit": "套",  "note": "含 1 年维护" },
        { "name": "定制开发（需求/团队/权限）", "quantity": 20, "unit_price": 1500,  "unit": "人天", "note": "按周迭代交付" },
        { "name": "培训与交付文档", "quantity": 2,  "unit_price": 2000,  "unit": "场",  "note": "线上/线下任选" }
      ],
      "note": "报价有效期 30 天；含税。"
    }'
)

echo "$META" | python -m json.tool
```

返回示例（字段会包含 `file_id` / `download_url`）：

```json
{
  "file_id": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.xlsx",
  "filename": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.xlsx",
  "download_url": "/api/files/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.xlsx?token=..."
}
```

#### 3) 下载生成的文件

```bash
DOWNLOAD_URL=$(echo "$META" | python -c 'import sys,json; print(json.load(sys.stdin)["download_url"])')

case "$DOWNLOAD_URL" in
  http*) FULL_URL="$DOWNLOAD_URL" ;;
  *)     FULL_URL="$API$DOWNLOAD_URL" ;;
esac

curl -L "$FULL_URL" -o quote.xlsx
```

#### 4) 生成 Word 报价单（可选）

把接口改为 `/api/docs/quote` 即可（入参相同）：

```bash
curl -sS -X POST "$API/api/docs/quote" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"seller":"某某科技有限公司","buyer":"某某客户有限公司","currency":"CNY","items":[{"name":"服务A","quantity":1,"unit_price":1000,"unit":"项"}]}' \
| python -m json.tool
```

## 7. 运行方式

### 7.1 推荐：一键启动前后端

```bash
pnpm dev
# 或
bash scripts/dev.sh
```

默认地址：

- Web: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/health`

### 7.2 分开启动

后端：

```bash
cp .env.example .env
cd backend
uv sync
uv run uvicorn jetlinks_ai_api.main:app --reload --port 8000
```

前端：

```bash
cd frontend
pnpm i
pnpm dev
```

### 7.3 前端构建后由后端托管

```bash
pnpm -C frontend build
# 然后访问 http://127.0.0.1:8000/
```

### 7.4 生产部署（Linux 单机示例）

目标：把前端构建产物交给后端托管，用户直接访问 `http(s)://<your-domain>/`（无需单独起 5173）。

#### 1) 准备环境

- Node.js `>= 22` + `pnpm`
- Python `>= 3.10` + `uv`

可选（用于 PPT/PDF 预览图）：

- LibreOffice（`soffice`）
- Poppler（`pdftoppm`）
- 中文字体（建议安装 `Noto Sans CJK` / 思源黑体，否则预览图可能会“丑/错位”）

#### 2) 配置 `.env`

至少需要：

- `OPENAI_API_KEY=...`（使用对话/Agent 时必需）
- `JETLINKS_AI_PUBLIC_BASE_URL=http://124.132.152.75:8000`（建议设置为你的对外域名/地址，用于生成绝对下载链接）
- 数据库（生产建议 Postgres）：`JETLINKS_AI_DB_URL=postgresql://user:pass@host:5432/db`
- （可选）`JETLINKS_AI_PPT_FONT=Noto Sans CJK SC`（Linux 服务器渲染/预览更稳定）

#### 3) 后端依赖 + 迁移

```bash
cd backend
uv sync
# 使用 Postgres 时执行迁移
uv run alembic upgrade head
```

#### 4) 构建前端

```bash
pnpm -C frontend i
pnpm -C frontend build
```

构建完成后，后端会自动挂载 `frontend/dist` 到 `/`。

#### 5) 启动后端（直接运行）

```bash
cd backend
uv run uvicorn jetlinks_ai_api.main:app --host 0.0.0.0 --port 8000
```

访问：

- Web（后端托管前端）：`http://<server>:8000/`
- API：`http://<server>:8000/api/*`

#### 6) systemd（可选，推荐）

示例（按需修改路径与用户）：

```ini
# /etc/systemd/system/codeskteam.service
[Unit]
Description=JetLinks AI (FastAPI)
After=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/codeskteam/backend
EnvironmentFile=/opt/codeskteam/.env
ExecStart=/opt/codeskteam/backend/.venv/bin/uvicorn jetlinks_ai_api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now codeskteam
sudo systemctl status codeskteam
```

## 8. 配置速查（`.env`）

模型与 provider：

- `JETLINKS_AI_PROVIDER=openai|codex|openclaw|mock|opencode|nanobot`
- `JETLINKS_AI_MODEL=gpt-5.2`
- `OPENAI_API_KEY=...`
- `OPENAI_BASE_URL=...`（兼容网关会自动补 `/v1`）

工作区与项目白名单：

- `JETLINKS_AI_WORKSPACE=/path/to/workspace`
- `JETLINKS_AI_PROJECTS_ROOT=/path/a,/path/b`

### 8.1 中央代码参考仓库（Reference Repo）

典型用法：公司/组织维护一份“中央代码参考仓库”（规范、脚手架、SDK、示例工程、最佳实践等），各团队在 JetLinks AI 里把它当作一个可选的“项目/工作区”来对话检索与引用。

它的实现逻辑是：

- 服务端用 `JETLINKS_AI_PROJECTS_ROOT` 定义“允许被团队添加”的目录白名单（默认等于 `JETLINKS_AI_WORKSPACE`）
- 团队 `owner/admin` 在「项目/工作区管理」里把中央仓库路径加入 `team_projects`（可用“一键导入项目”扫描后快速导入）
- 聊天时如果带 `project_id`，后端会把该项目的 `path` 作为本次对话的 `workspace_root`（Agent 的 `fs_list/fs_read/...` 等工具都在此目录内生效）
- 不带 `project_id` 时，则使用团队级的 `workspace_path`（`/api/team/settings`）或回退到服务端 `JETLINKS_AI_WORKSPACE`

建议：

- 让中央仓库路径对所有需要的团队都可见：把同一目录分别导入到各自团队的 `team_projects` 即可（按团队隔离的是“配置”，不是“文件夹拷贝”）
- 中央仓库不要放敏感信息（即使工具默认会拦截 `.env`，也可能存在其它敏感文件）
- 生产环境建议保持 `JETLINKS_AI_ENABLE_WRITE=0`，把“参考仓库”当只读使用（需要写入时再对特定团队/场景开启）

飞书预配置（可选）：

- `JETLINKS_AI_FEISHU_PRESET_NAME=团队飞书机器人`
- `JETLINKS_AI_FEISHU_PRESET_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxx`
- `JETLINKS_AI_FEISHU_PRESET_VERIFICATION_TOKEN=...`
- `JETLINKS_AI_FEISHU_PRESET_ENABLED=1`

安全开关：

- `JETLINKS_AI_ENABLE_SHELL=0|1`
- `JETLINKS_AI_ENABLE_WRITE=0|1`
- `JETLINKS_AI_ENABLE_BROWSER=0|1`
- `JETLINKS_AI_CODEX_ALLOW_DANGEROUS=0|1`（允许 Codex 无沙箱）

上下文与资源上限：

- `JETLINKS_AI_SESSION_TTL_MINUTES=120`
- `JETLINKS_AI_MAX_SESSIONS=200`
- `JETLINKS_AI_MAX_SESSION_MESSAGES=120`
- `JETLINKS_AI_MAX_CONTEXT_CHARS=120000`

存储：

- `JETLINKS_AI_DATA_DIR=.jetlinks-ai`
- `JETLINKS_AI_DB_PATH=.jetlinks-ai/jetlinks_ai.db`
- 若检测到旧目录 `.aistaff/aistaff.db`，且新目录 `.jetlinks-ai/jetlinks_ai.db` 尚不存在，服务首次启动时会自动把运行数据迁移到 `.jetlinks-ai/`。
- `JETLINKS_AI_OUTPUTS_DIR=.jetlinks-ai/outputs`
- `JETLINKS_AI_OUTPUTS_TTL_HOURS=168`

外部集成：

- `JETLINKS_AI_PUBLIC_BASE_URL=https://your-domain`
- `JETLINKS_AI_CODEX_CMD=codex`
- `JETLINKS_AI_CODEX_TIMEOUT_SECONDS=300`
- `JETLINKS_AI_CODEX_REASONING_EFFORT=medium`
- `JETLINKS_AI_OPENCODE_BASE_URL=http://127.0.0.1:4096`
- `JETLINKS_AI_NANOBOT_CMD=nanobot`

共享邀请码（内部使用，可多次注册）：

- `JETLINKS_AI_SHARED_INVITE_TOKEN=...`
- `JETLINKS_AI_SHARED_INVITE_TEAM_ID=...`（可选，限制只能加入指定团队）
- `JETLINKS_AI_SHARED_INVITE_TEAM_NAME=...`（可选）
- `JETLINKS_AI_SHARED_INVITE_ROLE=member`（默认 member；admin 需同时设置 `JETLINKS_AI_SHARED_INVITE_ALLOW_ADMIN=1`）

## 9. 登录与多团队

- 首次启动需 `setup` 初始化管理员与默认团队
- 登录后所有数据按团队隔离
- 忘记密码（本地）：`bash scripts/reset-password.sh <email>`

## 10. 扩展指南（从哪里改）

新增一个工具：

1. 在 `backend/jetlinks_ai_api/agent/tools/` 增加 tool 定义
2. 在 `AgentService._build_tools()` 注册
3. 如需前端展示，补充 `events` 解析与 UI 展示逻辑

新增一个业务接口：

1. `backend/jetlinks_ai_api/routers/` 新建 router
2. 业务逻辑写到 `services/`
3. 在 `main.py` 挂载
4. 前端 `frontend/src/api/` 增加客户端方法

新增 provider：

1. 实现 `ModelProvider` 或 provider service
2. 在 `AgentService` 选择分支接入
3. 补充 `.env.example` 和前端 provider 选项

## 11. 常见问题

`/api/chat` 返回 401：

- 检查登录态是否过期，前端会自动清空 token 并提示重新登录

文件能生成但下载失败：

- 检查 `JETLINKS_AI_PUBLIC_BASE_URL` 是否正确（外网场景尤其重要）

浏览器工具不可用：

- 开启 `JETLINKS_AI_ENABLE_BROWSER=1`
- 执行 `uv sync --extra browser && uv run playwright install chromium`

对话“像没记住上下文”：

- 确认是否复用了同一个 `session_id`
- 切换团队/项目/新会话会主动重置会话
- 过长历史会被 `JETLINKS_AI_MAX_CONTEXT_CHARS` 裁剪

---

如果你要进一步做架构演进，建议优先把 `README` 和 `backend/README` 保持同步，避免出现“入口文档”和“后端文档”描述不一致。

## 12. 许可证（开源协议）

推荐使用 **Apache License 2.0**（商业友好、含专利授权条款、公司开源常用）。

本项目采用 Apache-2.0 协议开源，详见 `LICENSE`。
