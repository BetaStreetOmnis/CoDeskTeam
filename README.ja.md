# aistaff

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

aistaff は、チーム向けの **セルフホスト可能な AI ワークスペース** です。  
**対話（チャット）駆動の実行** と **チーム運用（権限/分離）** を中心に設計しています。

- フロントエンド: Vue 3 + Vite
- バックエンド: FastAPI（認証、マルチチーム分離、Agent オーケストレーション、ファイル/ドキュメント）
- 内蔵: チャット + 履歴、アップロード/ダウンロード、ドキュメント生成（PPT/見積/検品）、プロトタイプ生成、Feishu/WeCom Webhook
- セキュアデフォルト: 高リスク機能（`shell/write/browser`）は **既定で無効**（必要時のみ有効化）

## クイックスタート

### 前提条件

- Node.js `>= 22` + `pnpm`
- Python `>= 3.10` + `uv`

任意:

- LibreOffice（PPT の表紙プレビュー画像生成に使用。PPTX 自体の生成は不要）
- Playwright（ブラウザツール用。既定で無効）

### 起動（推奨）

```bash
pnpm dev
# または
bash scripts/dev.sh
```

URL:

- Web: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/health`

初回は UI 上で **Setup** を完了し、最初の管理者ユーザーとチームを作成します。

### 最小設定

```bash
cp .env.example .env
```

チャット/Agent を使う場合は `.env` の `OPENAI_API_KEY` を設定してください。

## データベース（SQLite / Postgres）

- 既定: SQLite（追加設定なし）
- 本番推奨: `AISTAFF_DB_URL=postgresql://...` で Postgres を利用
- Postgres マイグレーション（Alembic）:

```bash
cd backend
uv run alembic upgrade head
```

バックエンド詳細: `backend/README.md`。

## 主な機能

- マルチチーム（ユーザー/チーム/招待/切替）
- チーム運用（プロジェクト、スキル/プロンプト、要件ボード）
- Provider: OpenAI / Codex / OpenCode / Nanobot
- ドキュメント生成:
  - PPTX（スタイル + レイアウト、PPT テンプレートをアップロードして `template_file_id` で反映）
  - 見積書（DOCX / XLSX）
  - 検品書（DOCX / XLSX）
- プロトタイプ生成（HTML ZIP + プレビュー）

## ライセンス

Apache-2.0（`LICENSE` を参照）。

