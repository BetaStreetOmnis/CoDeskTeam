# JetLinks AI · Enterprise OpenClaw Workspace

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

JetLinks AI is an open-source, self-hosted **AI delivery workspace for teams**.
You can think of it as an **enterprise-ready OpenClaw workspace**: chat-driven execution, shared team context, project / requirement management, deliverable automation, and OpenClaw operations in one product.

> From idea to execution to deliverables — chat, projects, docs, prototypes, and OpenClaw ops in one place.

> Acknowledgements: JetLinks AI includes optional integration points inspired by the OpenClaw gateway. Thanks to the OpenClaw project and community.

## Why teams like it

- **More than chat**: combine AI chat, team skills, requirement tracking, and project coordination in one workspace
- **Built for delivery**: generate PPTX, quotations, inspection sheets, prototypes, and posters without leaving the app
- **OpenClaw-ready**: manage gateway status, channel/plugin/skill sync, and team-scoped OpenClaw resources
- **Self-hosted and controllable**: FastAPI + Vue stack, SQLite/Postgres support, secure-by-default tool gating
- **Enterprise-friendly UX**: multi-team collaboration, workspace isolation, admin controls, and mobile-friendly layouts

## Highlights

- **Team-first workspace**: users, teams, invites, role-based operations, project/workspace switching
- **AI workbench**: chat, history, uploads/downloads, built-in skills, team prompt skills, shared context
- **Deliverable generation**: PPTX, quotation, inspection sheet, HTML prototype, SVG poster / long image
- **AI+ toolkit pipelines**: vision, media, content, office, and full-stack orchestration pipelines
- **OpenClaw operations center**: status probe, one-click sync, channel/plugin/skill management, team-scoped skill registry
- **Secure by default**: high-risk tools (`shell`, `write`, `browser`) are disabled unless explicitly enabled

## Architecture

- **Frontend**: Vue 3 + Vite
- **Backend**: FastAPI
- **Data**: SQLite by default, Postgres supported
- **Artifacts**: generated files are stored in `outputs/` or the configured runtime directory
- **Optional upstream integrations**: OpenClaw / OpenCode / Pi via vendored submodules

## Preview

![JetLinks AI · Enterprise OpenClaw Workspace](docs/images/github-hero.svg)

![JetLinks AI UI](docs/images/screenshot.png)

## Quick Start

### Prerequisites

- Node.js `>= 22` + `pnpm`
- Python `>= 3.10` + `uv`

Optional:

- LibreOffice (for PPT cover preview generation)
- Playwright (for browser tool and UI smoke testing)

### Run locally

```bash
pnpm dev
# or
bash scripts/dev.sh
```

Default URLs:

- Web: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/health`
- Ready: `http://127.0.0.1:8000/ready`

On first launch, complete the **Setup** flow in the UI to create the first admin user and team.

### Minimal configuration

```bash
cp .env.example .env
```

If you want chat / agent capability, set at least:

```bash
OPENAI_API_KEY=your-key
```

### Run with Docker (self-host)

This repo includes a simple Docker Compose setup (single container + SQLite by default):

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Default URL: `http://127.0.0.1:8001` (UI + API), health: `http://127.0.0.1:8001/health`.

More details: `docker/README.md`.

## Feature Map

### Workspace and team collaboration

- Multi-team user model with invites, memberships, and active-team switch
- Team workspace settings and project / repository management
- Team skills (prompt templates) and requirement board
- Cross-team delivery workflow with accept / reject states

### Built-in deliverables

- **PPTX** generation with template-based rendering
- **Quotation** generation in DOCX / XLSX
- **Inspection sheet** generation in DOCX / XLSX
- **Prototype** generation as HTML ZIP + preview
- **Poster / long image** generation as SVG via `/api/docs/poster`

### AI+ toolkit pipelines

Built-in skill catalog now includes pipeline-style capabilities:

- `vision`: image enhancement / conversion / resize-oriented flow
- `media`: short video / audio handling flow
- `content`: proposal, content-pack, and deliverable generation flow
- `office`: project / office automation flow
- `full`: combined end-to-end orchestration flow

### OpenClaw integration and ops

JetLinks AI now includes a team-facing OpenClaw operations area:

- Gateway status probing and runtime visibility
- One-click sync of discovered OpenClaw resources
- Team-scoped **channels / plugins / skills** CRUD
- Team-scoped OpenClaw skill discovery and counters
- Config editing experience aligned closer to original OpenClaw channel metadata structure

## Database

- Default: SQLite (zero extra setup)
- Production: Postgres via `JETLINKS_AI_DB_URL=postgresql://...`
- If an old `.aistaff/aistaff.db` exists and `.jetlinks-ai/jetlinks_ai.db` does not, JetLinks AI auto-migrates runtime data into `.jetlinks-ai/` on first start.

Run migrations for Postgres:

```bash
cd backend
uv run alembic upgrade head
```

More backend details: `backend/README.md`.

## Health and readiness

- `GET /health`: liveness check
- `GET /ready`: readiness check with DB/runtime path information
- `GET /api/ready`: API-scoped readiness endpoint

## API Example: Generate a quotation (XLSX / DOCX)

Notes:

- Quotation endpoints require auth: `Authorization: Bearer <access_token>`
- `download_url` is usually relative (for example `/api/files/...`)
- If `JETLINKS_AI_PUBLIC_BASE_URL` is configured, generated links become absolute URLs

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

### 2) Generate an XLSX quotation

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

## Integrations (optional)

This repo vendors optional upstream projects as git submodules:

- `third_party/openclaw`: OpenClaw gateway and multi-channel messaging
- `third_party/opencode`: OpenCode agent loop and approval flow
- `third_party/pi-mono`: Pi agent SDK / coding agent

If you need them:

```bash
git submodule update --init --recursive
```

### Pi provider

- Enable: `JETLINKS_AI_ENABLE_PI=1`
- Then select provider `pi` in the UI, or set `JETLINKS_AI_PROVIDER=pi`
- Requirements: Node.js `>= 20` or Docker via `JETLINKS_AI_PI_BACKEND=docker`

### OpenClaw gateway webhook

1. Create an integration token as team owner/admin:
   - `POST /api/team/integrations/openclaw`
2. Send messages from your gateway:
   - `POST /api/integrations/openclaw/message`
   - Header: `x-jetlinks-ai-integration-token: <token>`

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

## Testing

Frontend build:

```bash
pnpm -C frontend build
```

Backend tests:

```bash
cd backend
uv run python -m pytest
```

Useful smoke checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

## Production deployment

Goal: build the frontend and let the backend serve `frontend/dist` at `/` so users access a single host such as `https://your-domain/`.

### 1) Install prerequisites

- Node.js `>= 22` + `pnpm`
- Python `>= 3.10` + `uv`

Optional:

- LibreOffice (`soffice`)
- Poppler (`pdftoppm`)
- CJK fonts such as Noto Sans CJK / Source Han Sans

### 2) Configure `.env`

Recommended:

```bash
OPENAI_API_KEY=...
JETLINKS_AI_PUBLIC_BASE_URL=https://your-domain
```

More operational detail is available in `backend/README.md`.
