# JetLinks AI

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

JetLinks AI is an open-source, self-hosted **AI workspace for small teams and OPCs (one-person companies)**.
You can think of it as a **team-oriented OpenClaw**: chat-driven execution plus team governance, a shared workspace, and deliverable automation.

> Acknowledgements: JetLinks AI includes optional integration points inspired by the OpenClaw gateway. Thanks to the OpenClaw project and community.

- Frontend: Vue 3 + Vite
- Backend: FastAPI (auth, multi-team isolation, agent orchestration, file & doc services)
- Built-in: chat + history, uploads/downloads, document generation (PPT/quotation/inspection), prototype generation, Feishu/WeCom webhooks
- Optional: OpenClaw gateway ingress for multi-channel messaging
- Secure-by-default: high-risk tools (`shell/write/browser`) are **disabled by default** and must be explicitly enabled

## Screenshot

![JetLinks AI UI](docs/images/screenshot.png)

## Quick Start

### Prerequisites

- Node.js `>= 22` + `pnpm`
- Python `>= 3.10` + `uv` (backend dependency manager)

Optional:

- LibreOffice (for PPT cover preview image generation; PPTX generation works without it)
- Playwright (for browser tool; disabled by default)

### Run (recommended)

```bash
pnpm dev
# or
bash scripts/dev.sh
```

Default URLs:

- Web: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/health`

On first launch, complete the **Setup** flow in the UI to create the first admin user and team.

### Minimal configuration

```bash
cp .env.example .env
```

Then set `OPENAI_API_KEY` in `.env` if you want chat/agent capabilities.

## Database (SQLite / Postgres)

- Default: SQLite (no extra setup)
- Production: Postgres via `JETLINKS_AI_DB_URL=postgresql://...`
- Postgres migrations use Alembic:

```bash
cd backend
uv run alembic upgrade head
```

More backend details: `backend/README.md`.

## Features

- Multi-team: users, teams, memberships, invites, team switch
- Team workspace: projects, skills (prompt templates), requirements board
- Cross-team delivery: deliver a requirement to another team and let the target team accept/reject
- Agent providers: OpenAI / Pi (pi-mono) / Codex / OpenCode / Nanobot (via env + UI selection)
- Document generation:
  - PPTX: styles + layout modes, and **template-based rendering** by uploading a `.pptx` and passing `template_file_id`
  - Quotation: DOCX / XLSX
  - Inspection: DOCX / XLSX
- Prototype generator: produces an HTML ZIP + preview
- File service: uploads + tokenized downloads

## Cross-team requirement delivery

The requirements board uses the existing `team_requirements` statuses (`incoming/todo/in_progress/done/blocked`). When creating a requirement, you can optionally attach structured `delivery` info to **deliver** it to another team:

- Initiate delivery (source team `owner/admin`): create a requirement with `delivery.target_team_id`
  - The requirement is created under the **target team** (`team_id=target_team_id`)
  - Forced fields: `status=incoming`, `source_team=<source team name>`, `delivery_state=pending`
- Accept / reject (target team `owner/admin`):
  - Accept: `POST /api/team/requirements/{requirement_id}/accept` (`delivery_state=accepted`; if `status=incoming` it advances to `todo`)
  - Reject: `POST /api/team/requirements/{requirement_id}/reject` (`delivery_state=rejected`; rejected deliveries are hidden from the default list)

Note: delivery is currently **single-record mode** — the requirement exists only in the target team (no mirrored copy in the source team).

## Central reference repository (Reference Repo)

A common setup is to maintain a “central reference repo” (standards, templates, SDKs, examples) and let teams reference it as a selectable project/workspace:

- Server allowlist: `JETLINKS_AI_PROJECTS_ROOT` defines which directories teams are allowed to add (defaults to `JETLINKS_AI_WORKSPACE`)
- Team setup (team `owner/admin`): add the central repo path into `team_projects` via “Project/Workspace management” (or use “Quick import” to scan roots)
- Chat routing:
  - With `project_id`: the backend uses that project’s `path` as the chat `workspace_root` (tools like `fs_list/fs_read/...` run inside it)
  - Without `project_id`: uses the team workspace (`/api/team/settings`) or falls back to `JETLINKS_AI_WORKSPACE`

Recommendations:

- “Share” the same repo by adding the same path to each team’s `team_projects` (this shares config, not copies files)
- Keep it secret-free; in production prefer `JETLINKS_AI_ENABLE_WRITE=0` and treat it as read-only

## API Example: Generate a quotation (XLSX / DOCX)

Notes:

- The quotation endpoints require auth: `Authorization: Bearer <access_token>`
- `download_url` is usually a **relative path** (e.g. `/api/files/...`). If you set `JETLINKS_AI_PUBLIC_BASE_URL`, it becomes an absolute URL.

### 1) Login and get a token

```bash
API=http://127.0.0.1:8000

TOKEN=$(
  curl -sS -X POST "$API/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d '{"email":"admin@example.com","password":"your-password"}' \
  | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])'
)
```

### 2) Generate an XLSX quotation (recommended)

```bash
META=$(
  curl -sS -X POST "$API/api/docs/quote-xlsx" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{
      "seller": "ACME Co., Ltd.",
      "buyer": "Example Customer Inc.",
      "currency": "CNY",
      "items": [
        { "name": "Self-hosted deployment", "quantity": 1,  "unit_price": 68000, "unit": "set",  "note": "1 year support included" },
        { "name": "Customization (team/requirements)", "quantity": 20, "unit_price": 1500,  "unit": "day",  "note": "iterative delivery" },
        { "name": "Training + handover docs", "quantity": 2,  "unit_price": 2000,  "unit": "session" }
      ],
      "note": "Valid for 30 days."
    }'
)

echo "$META" | python -m json.tool
```

### 3) Download the generated file

```bash
DOWNLOAD_URL=$(echo "$META" | python -c 'import sys,json; print(json.load(sys.stdin)["download_url"])')

case "$DOWNLOAD_URL" in
  http*) FULL_URL="$DOWNLOAD_URL" ;;
  *)     FULL_URL="$API$DOWNLOAD_URL" ;;
esac

curl -L "$FULL_URL" -o quote.xlsx
```

### 4) Generate a DOCX quotation (optional)

Use `/api/docs/quote` with the same request body.

## Integrations (optional)

This repo vendors optional upstream projects as git submodules:

- `third_party/openclaw`: Moltbot/Clawdbot (gateway + multi-channel messaging)
- `third_party/opencode`: OpenCode (agent loop + approvals)
- `third_party/pi-mono`: Pi (agent SDK + coding agent)

If you need them:

```bash
git submodule update --init --recursive
```

### Pi (pi-mono) provider

- Enable: set `JETLINKS_AI_ENABLE_PI=1`, then select provider `pi` in the UI (or set `JETLINKS_AI_PROVIDER=pi`).
- Requirements: Node.js `>= 20` (or Docker via `JETLINKS_AI_PI_BACKEND=docker`).

### OpenClaw (gateway webhook)

1. Create an integration token (team owner/admin):

   - `POST /api/team/integrations/openclaw`

   2. Send messages from your gateway to JetLinks AI:

       - `POST /api/integrations/openclaw/message`
       - Header: `x-jetlinks-ai-integration-token: <token>` (legacy `x-aistaff-integration-token` is also accepted)

For now this is a simple HTTP ingress API. You can build a Moltbot plugin/bridge on top of it.

## Development

Backend only:

```bash
cd backend
uv sync
uv run uvicorn jetlinks_ai_api.main:app --reload --port 8000
```

Frontend only:

```bash
cd frontend
pnpm i
pnpm dev
```

## Production deployment (single host example)

Goal: build the frontend and let the backend serve `frontend/dist` at `/` so users only access `http(s)://<your-domain>/`.

### 1) Install prerequisites

- Node.js `>= 22` + `pnpm`
- Python `>= 3.10` + `uv`

Optional (PPT/PDF preview images):

- LibreOffice (`soffice`)
- Poppler (`pdftoppm`)
- CJK fonts (recommended: Noto Sans CJK / Source Han Sans) for better rendering in previews

### 2) Configure `.env`

Recommended:

- `OPENAI_API_KEY=...`
- `JETLINKS_AI_PUBLIC_BASE_URL=https://your-domain` (for absolute download links)
- `JETLINKS_AI_DB_URL=postgresql://user:pass@host:5432/db` (production recommended)
- (Optional) `JETLINKS_AI_PPT_FONT=Noto Sans CJK SC` (more consistent rendering on Linux)

### 3) Backend deps + migrations

```bash
cd backend
uv sync
uv run alembic upgrade head
```

### 4) Build frontend

```bash
pnpm -C frontend i
pnpm -C frontend build
```

### 5) Run backend

```bash
cd backend
uv run uvicorn jetlinks_ai_api.main:app --host 0.0.0.0 --port 8000
```

Open:

- UI: `http://<server>:8000/`
- API: `http://<server>:8000/api/*`

Tests (Postgres):

```bash
cd backend
uv run python -m pytest
```

Notes:

- By default tests start a temporary Postgres via Docker.
- To reuse an existing local Postgres, set `JETLINKS_AI_TEST_DB_URL=postgresql://...` before running pytest.

## Security

Server-side feature flags gate high-risk tools:

- `JETLINKS_AI_ENABLE_SHELL`
- `JETLINKS_AI_ENABLE_WRITE`
- `JETLINKS_AI_ENABLE_BROWSER`

Keep them off unless you trust the environment and users.

Internal signup code (optional):

- `JETLINKS_AI_SHARED_INVITE_TOKEN` enables a **multi-use** registration invite code. Do not expose it to the public internet.

## License

Apache-2.0. See `LICENSE`.
