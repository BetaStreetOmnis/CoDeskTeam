# CoDeskTeam API (FastAPI)

> Note: the Python package name is currently `aistaff_api` and env vars use `AISTAFF_*` for backward compatibility.

## 安装

```bash
cd backend
uv sync
```

可选：启用浏览器工具（Playwright）

```bash
uv sync --extra browser
uv run playwright install chromium
```

## 启动

```bash
cd backend
uv run uvicorn aistaff_api.main:app --reload --port 8000
```

## 数据库

- 默认：SQLite（`AISTAFF_DB_PATH`，默认 `../.aistaff/aistaff.db`）
- 生产推荐：Postgres（`AISTAFF_DB_URL=postgresql://user:pass@host:5432/db`）

## 迁移（Postgres / Alembic）

```bash
cd backend
# 需要环境变量里有 AISTAFF_DB_URL
uv run alembic upgrade head
```

## 测试（Postgres）

```bash
cd backend
uv run pytest
```

说明：

- 默认会用 Docker 启动临时 Postgres（无需本地安装 Postgres）。
- 如果想复用已有 Postgres：`AISTAFF_TEST_DB_URL=postgresql://... uv run pytest`
  - 为防误伤，非 localhost 需要额外加：`AISTAFF_TEST_DB_UNSAFE=1`
- 可指定测试镜像：`AISTAFF_TEST_PG_IMAGE=postgres:15`

## API

- 认证：
  - `GET /api/auth/status`（是否需要初始化）
  - `POST /api/auth/setup`（首次初始化管理员 + 默认团队）
  - `POST /api/auth/login`
  - `GET /api/me`
  - `POST /api/auth/switch-team`
- `POST /api/chat`
- `POST /api/docs/ppt`
- `POST /api/docs/quote`（DOCX）
- `POST /api/docs/quote-xlsx`（XLSX）
- `POST /api/prototype/generate`（HTML ZIP）
- `GET /api/skills`（内置技能清单）
- `GET /api/files/{file_id}`（下载生成的文件）
- 团队：
  - `GET/PUT /api/team/settings`（团队工作区）
  - `GET/POST/PUT/DELETE /api/team/projects`（项目/工作区）
  - `GET /api/team/projects/discover`（扫描 roots 发现项目）
  - `POST /api/team/projects/import`（批量导入项目）
  - `GET /api/team/skills` / `POST /api/team/skills` / `PUT /api/team/skills/{id}` / `DELETE /api/team/skills/{id}`
  - `GET/POST/PUT/DELETE /api/team/requirements`（需求页）
  - `POST /api/team/requirements/{requirement_id}/accept`（跨团队交付：接收）
  - `POST /api/team/requirements/{requirement_id}/reject`（跨团队交付：拒绝）
  - `GET /api/team/members` / `POST /api/team/members` / `PUT /api/team/members/{user_id}` / `DELETE /api/team/members/{user_id}`
  - `GET /api/team/integrations` / `POST /api/team/integrations/openclaw` / `DELETE /api/team/integrations/{token_id}`
- 集成（网关入口）：
  - `POST /api/integrations/openclaw/message`（Header: `x-aistaff-integration-token`）

## Pi（pi-mono，可选 Provider）

- 拉取子模块：`git submodule update --init --recursive`
- 启用：`AISTAFF_ENABLE_PI=1`，然后在 UI 选择 `provider=pi`（或设置 `AISTAFF_PROVIDER=pi`）
- 依赖：Node.js `>= 20`（或用 Docker：`AISTAFF_PI_BACKEND=docker`）

环境变量示例见仓库根目录 `.env.example`。
