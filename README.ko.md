# aistaff

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

aistaff는 팀을 위한 **자가 호스팅 가능한 AI 워크스페이스**입니다.  
**대화(채팅) 기반 실행**과 **팀 단위 운영/거버넌스(권한·격리)**를 중심으로 설계되었습니다.

- 프론트엔드: Vue 3 + Vite
- 백엔드: FastAPI(인증, 멀티팀 격리, 에이전트 오케스트레이션, 파일/문서 서비스)
- 내장 기능: 채팅 + 히스토리, 업로드/다운로드, 문서 생성(PPT/견적서/검수서), 프로토타입 생성, Feishu/WeCom Webhook
- 보안 기본값: 고위험 도구(`shell/write/browser`)는 **기본 비활성화**(필요 시에만 활성화)

## 빠른 시작

### 요구 사항

- Node.js `>= 22` + `pnpm`
- Python `>= 3.10` + `uv`

선택:

- LibreOffice(PPT 표지 프리뷰 이미지 생성용. PPTX 생성 자체에는 필수 아님)
- Playwright(브라우저 도구용. 기본 비활성화)

### 실행(권장)

```bash
pnpm dev
# 또는
bash scripts/dev.sh
```

기본 주소:

- Web: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/health`

첫 실행 시 UI에서 **Setup**을 완료하여 최초 관리자 계정과 팀을 생성합니다.

### 최소 설정

```bash
cp .env.example .env
```

채팅/에이전트를 사용하려면 `.env`의 `OPENAI_API_KEY`를 설정하세요.

## 데이터베이스(SQLite / Postgres)

- 기본: SQLite(추가 설정 없음)
- 운영 권장: `AISTAFF_DB_URL=postgresql://...`로 Postgres 사용
- Postgres 마이그레이션(Alembic):

```bash
cd backend
uv run alembic upgrade head
```

백엔드 상세: `backend/README.md`.

## 주요 기능

- 멀티팀(사용자/팀/초대/팀 전환)
- 팀 운영(프로젝트, 스킬/프롬프트, 요구사항 보드)
- Provider: OpenAI / Codex / OpenCode / Nanobot
- 문서 생성:
  - PPTX(스타일 + 레이아웃, PPT 템플릿 업로드 후 `template_file_id`로 반영)
  - 견적서(DOCX / XLSX)
  - 검수서(DOCX / XLSX)
- 프로토타입 생성(HTML ZIP + 프리뷰)

## 라이선스

Apache-2.0(`LICENSE` 참고).

