# CoDeskTeam

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

CoDeskTeam 是一个开源、可自托管的 **AI 工作台**，面向小团队与一人公司（OPC）。  
你可以把它理解为 **“团队/企业版的 OpenClaw”**：以对话驱动任务执行，在团队治理与交付物自动化场景里开箱即用。

> 鸣谢：本项目在网关/多渠道接入思路上参考了 OpenClaw，并提供可选的 OpenClaw ingress 集成入口。  

- 前端：Vue 3 + Vite（统一工作台、聊天、历史、项目/团队/需求管理）
- 后端：FastAPI（鉴权、多团队隔离、Agent 编排、文件与文档服务）
- 内置能力：对话与历史、文件上传/下载、文档生成（PPT/报价单/报检单）、原型生成、企业微信/飞书回调
- 可选能力：对接 OpenClaw 网关实现多渠道消息接入（作为 ingress）
- 安全默认：`shell/write/browser` 等高危工具默认关闭，需显式开启

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

### 3) 数据库（SQLite / Postgres）

- 默认使用 SQLite（无需额外配置）。
- 生产建议使用 Postgres：设置 `AISTAFF_DB_URL=postgresql://...`
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
  API --> OutDir[AISTAFF_OUTPUTS_DIR]

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
  - `AISTAFF_MAX_SESSION_MESSAGES`：限制历史消息条数
  - `AISTAFF_MAX_CONTEXT_CHARS`：按字符估算做近似裁剪

### 2.3 Provider 策略

- `openai`：走内置 `run_agent_task + tools` 全能力链路
- `codex`：走本机 `codex exec --json` 非交互链路（适合代码任务）
- `pi`：走 `pi-mono` 的 Coding Agent CLI（文本模式；需要 `AISTAFF_ENABLE_PI=1` + 子模块），适合代码/任务分解；对文档/PPT/原型/附件等场景会自动回退到内置 OpenAI 工具链
- `opencode` / `nanobot`：优先委托外部 Agent
- 对文档/PPT/原型/附件等场景，`opencode` 与 `nanobot` 会自动回退到内置 OpenAI 工具链，以保证产物能力一致
- provider 选择优先级：请求参数 `provider` > `.env` 中 `AISTAFF_PROVIDER` > 后端默认 `openai`

### 2.3.1 OpenClaw / OpenCode（可选集成）

- 本仓库包含三个可选上游子模块：
  - `third_party/openclaw`：Moltbot/Clawdbot（网关 + 多渠道消息能力）
  - `third_party/opencode`：OpenCode（Agent loop + approvals）
  - `third_party/pi-mono`：Pi（Agent SDK + Coding Agent）
- 拉取子模块：`git submodule update --init --recursive`
- OpenClaw 网关入口（HTTP）：
  1) 团队 `owner/admin` 生成 token：`POST /api/team/integrations/openclaw`
  2) 网关发消息：`POST /api/integrations/openclaw/message`（Header: `x-aistaff-integration-token`）

### 2.4 安全策略

- 服务端开关是能力上限：`AISTAFF_ENABLE_SHELL/WRITE/BROWSER`
- 前端只能在上限内“申请”能力，不能越权开启
- 高危能力仅团队 `owner/admin` 可启用
- 文件下载采用 JWT 下载令牌，不暴露裸文件路径
- Team/User 维度强隔离：会话、文件、技能、配置都绑定团队

### 2.5 可追溯与调试

- 聊天返回 `events`（工具调用、工具结果、裁剪、provider 事件）
- 历史会话可查看完整消息与事件
- 历史快照同步到 `.aistaff/history_sessions/`，支持目录检索（`/api/history/search`）

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
2. 输出文件写入 `AISTAFF_OUTPUTS_DIR`（默认 `.aistaff/outputs`）
3. 生成带 token 的 `download_url`
4. 建立 `file_records` 索引，支持历史检索与下载

## 4. 代码结构（按职责）

### 4.1 后端

- `backend/aistaff_api/main.py`：应用入口、路由挂载、生命周期
- `backend/aistaff_api/config.py`：环境变量与配置加载
- `backend/aistaff_api/deps.py`：依赖注入、鉴权上下文
- `backend/aistaff_api/db.py`：SQLite/Postgres schema 与访问辅助
- `backend/aistaff_api/routers/`：HTTP API
- `backend/aistaff_api/services/`：业务服务
- `backend/aistaff_api/agent/`：Agent 运行时、provider、tools
- `backend/aistaff_api/session_store.py`：会话内存存储

### 4.2 前端

- `frontend/src/App.vue`：主界面与主要交互编排
- `frontend/src/composables/useTeamWorkspaceState.ts`：团队/项目/技能/需求状态
- `frontend/src/composables/useHistoryState.ts`：会话与文件历史状态
- `frontend/src/api/*.ts`：API 客户端分模块封装

### 4.3 其他

- `roles/`：角色系统提示词模板
- `skills/`：技能模板
- `AISTAFF_OUTPUTS_DIR`：生成产物目录（默认 `.aistaff/outputs`）
- `.aistaff/`：运行期数据（DB、日志、JWT secret、历史快照）
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
- 返回的 `download_url` 默认是**相对路径**（如 `/api/files/...`）；如果你配置了 `AISTAFF_PUBLIC_BASE_URL`，则会返回绝对 URL

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
uv run uvicorn aistaff_api.main:app --reload --port 8000
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
- `AISTAFF_PUBLIC_BASE_URL=http://124.132.152.75:8000`（建议设置为你的对外域名/地址，用于生成绝对下载链接）
- 数据库（生产建议 Postgres）：`AISTAFF_DB_URL=postgresql://user:pass@host:5432/db`
- （可选）`AISTAFF_PPT_FONT=Noto Sans CJK SC`（Linux 服务器渲染/预览更稳定）

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
uv run uvicorn aistaff_api.main:app --host 0.0.0.0 --port 8000
```

访问：

- Web（后端托管前端）：`http://<server>:8000/`
- API：`http://<server>:8000/api/*`

#### 6) systemd（可选，推荐）

示例（按需修改路径与用户）：

```ini
# /etc/systemd/system/codeskteam.service
[Unit]
Description=CoDeskTeam (FastAPI)
After=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/codeskteam/backend
EnvironmentFile=/opt/codeskteam/.env
ExecStart=/opt/codeskteam/backend/.venv/bin/uvicorn aistaff_api.main:app --host 0.0.0.0 --port 8000
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

- `AISTAFF_PROVIDER=openai|codex|mock|opencode|nanobot`
- `AISTAFF_MODEL=gpt-5.2`
- `OPENAI_API_KEY=...`
- `OPENAI_BASE_URL=...`（兼容网关会自动补 `/v1`）

工作区与项目白名单：

- `AISTAFF_WORKSPACE=/path/to/workspace`
- `AISTAFF_PROJECTS_ROOT=/path/a,/path/b`

### 8.1 中央代码参考仓库（Reference Repo）

典型用法：公司/组织维护一份“中央代码参考仓库”（规范、脚手架、SDK、示例工程、最佳实践等），各团队在 CoDeskTeam 里把它当作一个可选的“项目/工作区”来对话检索与引用。

它的实现逻辑是：

- 服务端用 `AISTAFF_PROJECTS_ROOT` 定义“允许被团队添加”的目录白名单（默认等于 `AISTAFF_WORKSPACE`）
- 团队 `owner/admin` 在「项目/工作区管理」里把中央仓库路径加入 `team_projects`（可用“一键导入项目”扫描后快速导入）
- 聊天时如果带 `project_id`，后端会把该项目的 `path` 作为本次对话的 `workspace_root`（Agent 的 `fs_list/fs_read/...` 等工具都在此目录内生效）
- 不带 `project_id` 时，则使用团队级的 `workspace_path`（`/api/team/settings`）或回退到服务端 `AISTAFF_WORKSPACE`

建议：

- 让中央仓库路径对所有需要的团队都可见：把同一目录分别导入到各自团队的 `team_projects` 即可（按团队隔离的是“配置”，不是“文件夹拷贝”）
- 中央仓库不要放敏感信息（即使工具默认会拦截 `.env`，也可能存在其它敏感文件）
- 生产环境建议保持 `AISTAFF_ENABLE_WRITE=0`，把“参考仓库”当只读使用（需要写入时再对特定团队/场景开启）

飞书预配置（可选）：

- `AISTAFF_FEISHU_PRESET_NAME=团队飞书机器人`
- `AISTAFF_FEISHU_PRESET_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxx`
- `AISTAFF_FEISHU_PRESET_VERIFICATION_TOKEN=...`
- `AISTAFF_FEISHU_PRESET_ENABLED=1`

安全开关：

- `AISTAFF_ENABLE_SHELL=0|1`
- `AISTAFF_ENABLE_WRITE=0|1`
- `AISTAFF_ENABLE_BROWSER=0|1`
- `AISTAFF_CODEX_ALLOW_DANGEROUS=0|1`（允许 Codex 无沙箱）

上下文与资源上限：

- `AISTAFF_SESSION_TTL_MINUTES=120`
- `AISTAFF_MAX_SESSIONS=200`
- `AISTAFF_MAX_SESSION_MESSAGES=120`
- `AISTAFF_MAX_CONTEXT_CHARS=120000`

存储：

- `AISTAFF_DATA_DIR=.aistaff`
- `AISTAFF_DB_PATH=.aistaff/aistaff.db`
- `AISTAFF_OUTPUTS_DIR=.aistaff/outputs`
- `AISTAFF_OUTPUTS_TTL_HOURS=168`

外部集成：

- `AISTAFF_PUBLIC_BASE_URL=https://your-domain`
- `AISTAFF_CODEX_CMD=codex`
- `AISTAFF_CODEX_TIMEOUT_SECONDS=300`
- `AISTAFF_CODEX_REASONING_EFFORT=medium`
- `AISTAFF_OPENCODE_BASE_URL=http://127.0.0.1:4096`
- `AISTAFF_NANOBOT_CMD=nanobot`

共享邀请码（内部使用，可多次注册）：

- `AISTAFF_SHARED_INVITE_TOKEN=...`
- `AISTAFF_SHARED_INVITE_TEAM_ID=...`（可选，限制只能加入指定团队）
- `AISTAFF_SHARED_INVITE_TEAM_NAME=...`（可选）
- `AISTAFF_SHARED_INVITE_ROLE=member`（默认 member；admin 需同时设置 `AISTAFF_SHARED_INVITE_ALLOW_ADMIN=1`）

## 9. 登录与多团队

- 首次启动需 `setup` 初始化管理员与默认团队
- 登录后所有数据按团队隔离
- 忘记密码（本地）：`bash scripts/reset-password.sh <email>`

## 10. 扩展指南（从哪里改）

新增一个工具：

1. 在 `backend/aistaff_api/agent/tools/` 增加 tool 定义
2. 在 `AgentService._build_tools()` 注册
3. 如需前端展示，补充 `events` 解析与 UI 展示逻辑

新增一个业务接口：

1. `backend/aistaff_api/routers/` 新建 router
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

- 检查 `AISTAFF_PUBLIC_BASE_URL` 是否正确（外网场景尤其重要）

浏览器工具不可用：

- 开启 `AISTAFF_ENABLE_BROWSER=1`
- 执行 `uv sync --extra browser && uv run playwright install chromium`

对话“像没记住上下文”：

- 确认是否复用了同一个 `session_id`
- 切换团队/项目/新会话会主动重置会话
- 过长历史会被 `AISTAFF_MAX_CONTEXT_CHARS` 裁剪

---

如果你要进一步做架构演进，建议优先把 `README` 和 `backend/README` 保持同步，避免出现“入口文档”和“后端文档”描述不一致。

## 12. 许可证（开源协议）

推荐使用 **Apache License 2.0**（商业友好、含专利授权条款、公司开源常用）。

本项目采用 Apache-2.0 协议开源，详见 `LICENSE`。
