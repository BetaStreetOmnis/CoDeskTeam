from __future__ import annotations

import base64
import io


async def _setup_token(client) -> str:  # noqa: ANN001
    resp = await client.post(
        "/api/auth/setup",
        json={
            "team_name": "Pipeline 团队",
            "name": "Owner",
            "email": "owner@example.com",
            "password": "password123",
        },
    )
    assert resp.status_code == 200
    token = str(resp.json().get("access_token") or "")
    assert token
    return token


async def test_skills_list_contains_pipeline_entries(client) -> None:  # noqa: ANN001
    token = await _setup_token(client)
    resp = await client.get("/api/skills", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    ids = {str(item.get("id")) for item in body if isinstance(item, dict)}
    assert "pipeline_fullstack" in ids
    assert "pipeline_vision" in ids
    assert "pipeline_media" in ids
    assert "pipeline_content" in ids
    assert "pipeline_office" in ids


async def test_content_pipeline_runs_and_returns_artifacts(client) -> None:  # noqa: ANN001
    token = await _setup_token(client)
    resp = await client.post(
        "/api/skills/pipeline/content",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "deployment_mode": "hybrid",
            "topic": "测试内容 Pipeline",
            "audience": "测试团队",
            "tone": "专业",
            "key_points": ["云边协同", "技能化执行"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("pipeline_id") == "content"
    assert isinstance(body.get("artifacts"), list)
    assert len(body["artifacts"]) >= 1
    download = str(body.get("download_url") or "")
    assert download.startswith("http") or download.startswith("/api/files/")


async def test_content_pipeline_supports_rewrite_and_multilang(client) -> None:  # noqa: ANN001
    token = await _setup_token(client)
    resp = await client.post(
        "/api/skills/pipeline/content",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "deployment_mode": "hybrid",
            "topic": "内容升级",
            "audience": "交付团队",
            "tone": "专业",
            "key_points": ["多语输出", "版本摘要"],
            "languages": ["zh-CN", "en-US"],
            "variants": 2,
            "source_text": "这是原始文稿，主要介绍内容升级方案。",
            "review_focus": ["结构层级", "可读性"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    filenames = {str(item.get("filename") or "") for item in body.get("artifacts") or [] if isinstance(item, dict)}
    assert any(name.endswith(".md") for name in filenames)
    assert any(name.endswith(".docx") for name in filenames)


async def test_office_pipeline_supports_schedule_and_conversion(client) -> None:  # noqa: ANN001
    token = await _setup_token(client)
    upload = await client.post(
        "/api/files/upload-file",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("notes.csv", io.BytesIO(b"title,owner\nTask A,PM\n"), "text/csv")},
    )
    assert upload.status_code == 200
    file_id = str(upload.json().get("file_id") or "")
    assert file_id

    resp = await client.post(
        "/api/skills/pipeline/office",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "deployment_mode": "hybrid",
            "project_name": "办公联动测试",
            "input_file_ids": [file_id],
            "tasks": [{"title": "需求确认", "owner": "PM", "due_date": "本周", "priority": "high", "status": "todo"}],
            "schedule_items": [
                {"title": "评审会", "owner": "PM", "start": "2026-03-18 10:00", "end": "2026-03-18 11:00", "location": "线上"},
                {"title": "联调会", "owner": "研发", "start": "2026-03-18 10:30", "end": "2026-03-18 11:30", "location": "线上"},
            ],
            "meeting_notes": "确认本周完成需求确认，下周进入联调。",
            "file_conversion_targets": ["json", "xlsx"],
            "reminder_hours": [24, 2],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    filenames = [str(item.get("filename") or "") for item in body.get("artifacts") or [] if isinstance(item, dict)]
    assert any(name.endswith(".ics") for name in filenames)
    assert any(name.endswith(".xlsx") for name in filenames)
    assert any("manifest" in name or name.endswith(".md") for name in filenames)


async def test_vision_pipeline_falls_back_when_edit_endpoint_missing(client, monkeypatch) -> None:  # noqa: ANN001
    from PIL import Image

    from jetlinks_ai_api.agent.providers.base import ModelResponse
    from jetlinks_ai_api.services import toolkit_pipeline_service as svc_mod

    token = await _setup_token(client)
    img = Image.new("RGB", (128, 128), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    upload = await client.post(
        "/api/files/upload-image",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("edit.png", io.BytesIO(buf.getvalue()), "image/png")},
    )
    assert upload.status_code == 200
    file_id = str(upload.json().get("file_id") or "")
    assert file_id

    out = io.BytesIO()
    Image.new("RGB", (64, 64), (120, 180, 255)).save(out, format="PNG")
    b64_image = base64.b64encode(out.getvalue()).decode("ascii")

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict | None = None) -> None:
            self.status_code = status_code
            self._payload = payload or {}
            self.headers = {"content-type": "application/json"}
            self.text = str(self._payload)

        def json(self) -> dict:
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN003
            pass

        async def __aenter__(self):  # noqa: ANN204
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
            return None

        async def post(self, url: str, **kwargs):  # noqa: ANN003, ANN201
            if url.endswith("/images/edits"):
                return FakeResponse(404, {"message": "Cannot POST /openai/v1/images/edits", "error": "Not Found"})
            if url.endswith("/images/generations"):
                return FakeResponse(200, {"data": [{"b64_json": b64_image}]})
            raise AssertionError(f"unexpected url: {url}")

        async def get(self, url: str, **kwargs):  # noqa: ANN003, ANN201
            raise AssertionError(f"unexpected get: {url}")

    async def fake_complete(self, *args, **kwargs):  # noqa: ANN001, ANN202
        return ModelResponse(assistant_text="保留原图主体，蓝紫科技风，发光边缘，玻璃质感图标", tool_calls=[])

    monkeypatch.setenv("JETLINKS_AI_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("JETLINKS_AI_OPENAI_BASE_URL", "https://example.com/openai")
    monkeypatch.setattr(svc_mod.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(svc_mod.OpenAiProvider, "complete", fake_complete)

    resp = await client.post(
        "/api/skills/pipeline/vision",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "deployment_mode": "cloud",
            "operation": "edit",
            "prompt": "把图片改成科技风",
            "input_file_ids": [file_id],
            "target_formats": ["png"],
            "enhance": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    filenames = [str(item.get("filename") or "") for item in body.get("artifacts") or [] if isinstance(item, dict)]
    assert any(name.endswith(".png") for name in filenames)
    assert any("自动回退为参考图理解后再生成" in str(item) for item in body.get("warnings") or [])
