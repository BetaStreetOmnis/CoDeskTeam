from __future__ import annotations

import html
import re
import zipfile
from uuid import uuid4

from ..config import Settings
from ..output_cleanup import maybe_cleanup_outputs_dir
from ..url_utils import abs_url
from .auth_service import create_download_token


def _slugify(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9\s_-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")


def _esc(text: object) -> str:
    return html.escape(str(text or ""), quote=True)


def _render_index(project_name: str, pages: list[dict]) -> str:
    links = "\n".join(
        [
            f'<a class="card" href="{_esc(p["filename"])}"><div class="title">{_esc(p["title"])}</div><div class="desc">{_esc(p.get("description",""))}</div></a>'
            for p in pages
        ]
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{_esc(project_name)} - 原型</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif; background:#f5f7fa; color:#111827; }}
    .top {{ height:64px; display:flex; align-items:center; padding:0 24px; background:#fff; box-shadow:0 2px 8px rgba(0,0,0,.06); position:sticky; top:0; }}
    .brand {{ font-weight:700; color:#1890ff; }}
    .wrap {{ max-width:1100px; margin:0 auto; padding:24px; }}
    h1 {{ margin: 12px 0 6px; font-size:22px; }}
    .hint {{ color:#6b7280; font-size:13px; margin-bottom:16px; }}
    .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap:12px; }}
    .card {{ display:block; padding:14px 14px; border-radius:12px; background:#fff; border:1px solid #e5e7eb; text-decoration:none; color:inherit; }}
    .card:hover {{ border-color:#93c5fd; box-shadow:0 4px 18px rgba(24,144,255,.12); }}
    .title {{ font-weight:600; margin-bottom:6px; }}
    .desc {{ color:#6b7280; font-size:13px; line-height:1.5; }}
  </style>
</head>
<body>
  <div class="top"><div class="brand">{_esc(project_name)}</div></div>
  <div class="wrap">
    <h1>原型页面</h1>
    <div class="hint">风格参考：你提供的脚本生成页面（清爽后台风 + 卡片/表格 + 蓝色主色）。</div>
    <div class="grid">
      {links}
    </div>
  </div>
</body>
</html>
"""


def _render_page(project_name: str, pages: list[dict], current: dict) -> str:
    nav_links = "\n".join(
        [
            f'<a class="nav-item {"active" if p["filename"]==current["filename"] else ""}" href="{_esc(p["filename"])}">{_esc(p["title"])}</a>'
            for p in pages
        ]
    )

    page_title = current["title"]
    page_desc = current.get("description") or "这里是页面说明，可替换为真实业务描述。"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{_esc(page_title)} - {_esc(project_name)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif; background:#f5f7fa; color:#111827; }}
    .top {{ height:64px; display:flex; align-items:center; padding:0 24px; background:#fff; box-shadow:0 2px 8px rgba(0,0,0,.06); position:fixed; top:0; left:0; right:0; z-index:10; }}
    .brand {{ font-weight:700; color:#1890ff; }}
    .layout {{ display:flex; min-height:100vh; }}
    .side {{ width:240px; padding:16px; background:#fff; border-right:1px solid #e5e7eb; position:fixed; top:64px; bottom:0; overflow:auto; }}
    .nav-title {{ font-size:12px; color:#6b7280; margin:8px 6px; }}
    .nav-item {{ display:block; padding:10px 10px; border-radius:10px; text-decoration:none; color:#111827; }}
    .nav-item:hover {{ background:#f3f4f6; }}
    .nav-item.active {{ background:#e8f3ff; color:#0b66c3; font-weight:600; }}
    .main {{ margin-left:240px; padding:24px; padding-top:88px; width:100%; }}
    .card {{ background:#fff; border:1px solid #e5e7eb; border-radius:12px; padding:14px; }}
    .header {{ margin-bottom:12px; }}
    .h1 {{ font-size:22px; font-weight:700; margin:0 0 6px; }}
    .desc {{ color:#6b7280; font-size:13px; line-height:1.6; }}
    .stats {{ display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:12px; margin-top:12px; }}
    @media (max-width: 900px) {{
      .side {{ position:static; width:100%; border-right:0; border-bottom:1px solid #e5e7eb; }}
      .main {{ margin-left:0; padding-top:24px; }}
      .top {{ position:sticky; }}
      .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    .stat-k {{ color:#6b7280; font-size:12px; }}
    .stat-v {{ font-size:20px; font-weight:700; margin-top:6px; }}
    .table {{ width:100%; border-collapse:collapse; margin-top:12px; }}
    .table th, .table td {{ border-bottom:1px solid #e5e7eb; padding:10px 8px; text-align:left; font-size:13px; }}
    .table th {{ color:#374151; font-weight:600; background:#fafafa; }}
    .badge {{ padding:2px 8px; border-radius:999px; font-size:12px; border:1px solid transparent; display:inline-block; }}
    .success {{ background:#ecfdf5; color:#065f46; border-color:#a7f3d0; }}
    .warning {{ background:#fffbeb; color:#92400e; border-color:#fde68a; }}
    .error {{ background:#fef2f2; color:#991b1b; border-color:#fecaca; }}
  </style>
</head>
<body>
  <div class="top"><div class="brand">{_esc(project_name)}</div></div>
  <div class="layout">
    <aside class="side">
      <div class="nav-title">页面导航</div>
      {nav_links}
      <div class="nav-title">入口</div>
      <a class="nav-item" href="index.html">返回首页</a>
    </aside>
    <main class="main">
      <div class="card header">
        <div class="h1">{_esc(page_title)}</div>
        <div class="desc">{_esc(page_desc)}</div>
        <div class="stats">
          <div class="card"><div class="stat-k">总数</div><div class="stat-v">128</div></div>
          <div class="card"><div class="stat-k">正常</div><div class="stat-v">120</div></div>
          <div class="card"><div class="stat-k">告警</div><div class="stat-v">6</div></div>
          <div class="card"><div class="stat-k">处理中</div><div class="stat-v">2</div></div>
        </div>
      </div>

      <div class="card">
        <table class="table">
          <thead>
            <tr>
              <th>名称</th>
              <th>类型</th>
              <th>更新时间</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>示例数据 A</td><td>配置</td><td>2026-02-03</td><td><span class="badge success">正常</span></td></tr>
            <tr><td>示例数据 B</td><td>记录</td><td>2026-02-03</td><td><span class="badge warning">告警</span></td></tr>
            <tr><td>示例数据 C</td><td>任务</td><td>2026-02-03</td><td><span class="badge error">异常</span></td></tr>
          </tbody>
        </table>
      </div>
    </main>
  </div>
</body>
</html>
"""


class PrototypeService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._settings.outputs_dir.mkdir(parents=True, exist_ok=True)
        maybe_cleanup_outputs_dir(
            self._settings.outputs_dir,
            ttl_seconds=max(0, int(self._settings.outputs_ttl_hours)) * 3600,
        )


    async def generate(self, *, project_name: str, pages: list[dict]) -> dict:
        if not project_name.strip():
            raise ValueError("project_name is empty")
        if not pages:
            raise ValueError("pages is empty")

        bundle_id = uuid4().hex
        bundle_dir = (self._settings.outputs_dir / f"prototype_{bundle_id}").resolve()
        bundle_dir.mkdir(parents=True, exist_ok=True)

        normalized: list[dict] = []
        used = set()
        for idx, p in enumerate(pages, 1):
            title = str(p.get("title") or "").strip()
            if not title:
                continue
            slug_source = str(p.get("slug") or title)
            slug = _slugify(slug_source)
            if not slug:
                slug = f"page-{idx:02d}"
            filename = f"{slug}.html"
            # ensure unique
            while filename in used:
                filename = f"{slug}-{uuid4().hex[:4]}.html"
            used.add(filename)
            normalized.append({"title": title, "description": str(p.get("description") or ""), "filename": filename})

        if not normalized:
            raise ValueError("no valid pages")

        (bundle_dir / "index.html").write_text(_render_index(project_name, normalized), encoding="utf-8")
        for p in normalized:
            (bundle_dir / p["filename"]).write_text(_render_page(project_name, normalized, p), encoding="utf-8")

        zip_name = f"{bundle_id}.zip"
        zip_path = (self._settings.outputs_dir / zip_name).resolve()

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in bundle_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, arcname=file_path.relative_to(bundle_dir))

        file_id = zip_name
        token = create_download_token(settings=self._settings, file_id=file_id)
        preview_id = bundle_dir.name
        preview_token = create_download_token(settings=self._settings, file_id=preview_id)
        return {
            "file_id": file_id,
            "filename": zip_name,
            "download_url": abs_url(self._settings, f"/api/files/{file_id}?token={token}"),
            "preview_url": abs_url(self._settings, f"/api/prototype/preview/{preview_id}/index.html?token={preview_token}"),
        }
