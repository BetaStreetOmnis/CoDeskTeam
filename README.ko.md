# CoDeskTeam

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

CoDeskTeam은 팀을 위한 **자가 호스팅 가능한 AI 워크스페이스**입니다.  
**대화(채팅) 기반 실행**과 **팀 단위 운영/거버넌스(권한·격리)**를 중심으로 설계되었습니다.

> 참고: 현재 코드베이스 내부에서는 `aistaff` 명명(환경 변수 `AISTAFF_*`, Python 패키지 `aistaff_api`)을 그대로 사용합니다. 사용에는 영향 없습니다.

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
- 팀 간 전달(Delivery): 요구사항을 다른 팀으로 전달하고 대상 팀이 수락/거절
- Provider: OpenAI / Pi(pi-mono) / Codex / OpenCode / Nanobot
- 문서 생성:
  - PPTX(스타일 + 레이아웃, PPT 템플릿 업로드 후 `template_file_id`로 반영)
  - 견적서(DOCX / XLSX)
  - 검수서(DOCX / XLSX)
- 프로토타입 생성(HTML ZIP + 프리뷰)

## 팀 간 요구사항 전달(Delivery)

요구사항 보드는 기존 `team_requirements` 상태(`incoming/todo/in_progress/done/blocked`)를 사용합니다. 요구사항 생성 시 구조화된 `delivery` 정보를 선택적으로 포함하면, 요구사항을 **다른 팀으로 전달**할 수 있습니다.

- 전달 발신(발신 팀 `owner/admin`): `delivery.target_team_id`를 포함해 요구사항 생성
  - 요구사항은 **대상 팀**에 생성됩니다(`team_id=target_team_id`)
  - 강제 설정: `status=incoming`, `source_team=<발신 팀 이름>`, `delivery_state=pending`
- 수락/거절(대상 팀 `owner/admin`):
  - 수락: `POST /api/team/requirements/{requirement_id}/accept` (`delivery_state=accepted`; `status=incoming`이면 `todo`로 진행)
  - 거절: `POST /api/team/requirements/{requirement_id}/reject` (`delivery_state=rejected`; 거절된 전달은 기본 목록에서 숨김)

참고: 현재는 **단일 레코드 방식**입니다. 요구사항은 대상 팀에만 존재하며, 발신 팀에 자동 미러를 만들지 않습니다.

## 중앙 코드 레퍼런스 저장소(Reference Repo)

사내 “중앙 레퍼런스 저장소”(규정, 템플릿, SDK, 예제 등)를 유지하고, 각 팀이 선택 가능한 프로젝트/워크스페이스로 참조하는 구성이 가능합니다.

- 서버 허용 목록: `AISTAFF_PROJECTS_ROOT`가 팀이 추가할 수 있는 디렉터리 화이트리스트를 정의합니다(기본값은 `AISTAFF_WORKSPACE`)
- 팀 설정(팀 `owner/admin`): UI의 “프로젝트/워크스페이스 관리”에서 중앙 저장소 경로를 `team_projects`에 추가(“프로젝트 일괄 가져오기”로 roots 스캔 후 빠르게 추가 가능)
- 채팅 적용:
  - `project_id` 있음: 해당 프로젝트의 `path`를 `workspace_root`로 사용(`fs_list/fs_read/...` 등의 도구가 그 하위에서 실행)
  - `project_id` 없음: 팀 워크스페이스(`/api/team/settings`)를 사용하거나, 미설정 시 `AISTAFF_WORKSPACE`로 폴백

권장:

- 같은 저장소를 “공유”하려면 각 팀의 `team_projects`에 동일한 경로를 추가하면 됩니다(설정만 팀별로 분리되며 파일을 복사하지 않음)
- 비밀 정보는 두지 말고, 운영 환경에서는 `AISTAFF_ENABLE_WRITE=0`을 기본으로 두어 참조(읽기) 용도로 사용하는 것을 권장합니다

## API 예시: 견적서 생성(XLSX / DOCX)

참고:

- 견적서 엔드포인트는 인증이 필요합니다: `Authorization: Bearer <access_token>`
- `download_url`은 보통 **상대 경로**(예: `/api/files/...`)입니다. `AISTAFF_PUBLIC_BASE_URL`을 설정하면 절대 URL로 반환됩니다.

### 1) 로그인해서 token 받기

```bash
API=http://127.0.0.1:8000

TOKEN=$(
  curl -sS -X POST "$API/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d '{"email":"admin@example.com","password":"your-password"}' \
  | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])'
)
```

### 2) XLSX 견적서 생성(권장)

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
        { "name": "Customization (team/requirements)", "quantity": 20, "unit_price": 1500,  "unit": "day",  "note": "iterative delivery" }
      ],
      "note": "Valid for 30 days."
    }'
)

echo "$META" | python -m json.tool
```

### 3) 생성된 파일 다운로드

```bash
DOWNLOAD_URL=$(echo "$META" | python -c 'import sys,json; print(json.load(sys.stdin)["download_url"])')

case "$DOWNLOAD_URL" in
  http*) FULL_URL="$DOWNLOAD_URL" ;;
  *)     FULL_URL="$API$DOWNLOAD_URL" ;;
esac

curl -L "$FULL_URL" -o quote.xlsx
```

### 4) DOCX(선택)

동일한 요청 바디로 `/api/docs/quote`를 호출하면 됩니다.

## 라이선스

Apache-2.0(`LICENSE` 참고).
