# aistaff

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

aistaff is a self-hostable **AI workspace for teams**, built around **chat-driven execution + team governance**.

- Frontend: Vue 3 + Vite
- Backend: FastAPI (auth, multi-team isolation, agent orchestration, file & doc services)
- Built-in: chat + history, uploads/downloads, document generation (PPT/quotation/inspection), prototype generation, Feishu/WeCom webhooks
- Secure-by-default: high-risk tools (`shell/write/browser`) are **disabled by default** and must be explicitly enabled

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
- Production: Postgres via `AISTAFF_DB_URL=postgresql://...`
- Postgres migrations use Alembic:

```bash
cd backend
uv run alembic upgrade head
```

More backend details: `backend/README.md`.

## Features

- Multi-team: users, teams, memberships, invites, team switch
- Team workspace: projects, skills (prompt templates), requirements board
- Agent providers: OpenAI / Codex / OpenCode / Nanobot (via env + UI selection)
- Document generation:
  - PPTX: styles + layout modes, and **template-based rendering** by uploading a `.pptx` and passing `template_file_id`
  - Quotation: DOCX / XLSX
  - Inspection: DOCX / XLSX
- Prototype generator: produces an HTML ZIP + preview
- File service: uploads + tokenized downloads

## Development

Backend only:

```bash
cd backend
uv sync
uv run uvicorn aistaff_api.main:app --reload --port 8000
```

Frontend only:

```bash
cd frontend
pnpm i
pnpm dev
```

Tests (Postgres):

```bash
cd backend
uv run pytest
```

Notes:

- By default tests start a temporary Postgres via Docker.
- To reuse an existing local Postgres, set `AISTAFF_TEST_DB_URL=postgresql://...` before running pytest.

## Security

Server-side feature flags gate high-risk tools:

- `AISTAFF_ENABLE_SHELL`
- `AISTAFF_ENABLE_WRITE`
- `AISTAFF_ENABLE_BROWSER`

Keep them off unless you trust the environment and users.

## License

Apache-2.0. See `LICENSE`.

