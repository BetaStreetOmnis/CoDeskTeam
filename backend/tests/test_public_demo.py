from __future__ import annotations

import json

import httpx


def _read_jsonl(path) -> list[dict]:  # noqa: ANN001
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


async def test_public_demo_auth_returns_token(migrated_pg_url: str, tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("JETLINKS_AI_DB_URL", migrated_pg_url)
    monkeypatch.setenv("JETLINKS_AI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JETLINKS_AI_OUTPUTS_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("JETLINKS_AI_JWT_SECRET", "test-jwt-secret-0123456789abcdef0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("JETLINKS_AI_PUBLIC_DEMO_ENABLED", "1")
    monkeypatch.setenv("JETLINKS_AI_PUBLIC_DEMO_TEAM_NAME", "公开演示团队")
    monkeypatch.setenv("JETLINKS_AI_PUBLIC_DEMO_USER_EMAIL", "demo@example.com")
    monkeypatch.setenv("JETLINKS_AI_PUBLIC_DEMO_USER_NAME", "Demo Visitor")
    monkeypatch.setenv("JETLINKS_AI_SUPER_ALL", "1")
    audit_path = tmp_path / "data" / "logs" / "public_demo_audit.jsonl"

    from jetlinks_ai_api.app_factory import create_app
    from jetlinks_ai_api.config import load_settings

    app = create_app(load_settings())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        demo_resp = await client.get("/api/auth/demo")
        assert demo_resp.status_code == 200
        body = demo_resp.json()
        assert body["user"]["email"] == "demo@example.com"
        assert body["active_team"]["name"] == "公开演示团队"
        token = str(body.get("access_token") or "")
        assert token

        me_resp = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200
        assert me_resp.json()["active_team"]["role"] == "member"
        assert me_resp.json()["is_super_admin"] is False
    audit_rows = _read_jsonl(audit_path)
    assert any(row["event"] == "demo_auth_issued" and row["path"] == "/api/auth/demo" for row in audit_rows)


async def test_public_demo_auth_rate_limited(migrated_pg_url: str, tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("JETLINKS_AI_DB_URL", migrated_pg_url)
    monkeypatch.setenv("JETLINKS_AI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JETLINKS_AI_OUTPUTS_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("JETLINKS_AI_JWT_SECRET", "test-jwt-secret-0123456789abcdef0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("JETLINKS_AI_PUBLIC_DEMO_ENABLED", "1")
    monkeypatch.setenv("JETLINKS_AI_PUBLIC_DEMO_AUTH_MAX_REQUESTS", "1")
    monkeypatch.setenv("JETLINKS_AI_PUBLIC_DEMO_AUTH_WINDOW_SECONDS", "300")
    audit_path = tmp_path / "data" / "logs" / "public_demo_audit.jsonl"

    from jetlinks_ai_api.app_factory import create_app
    from jetlinks_ai_api.config import load_settings

    app = create_app(load_settings())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get("/api/auth/demo")
        assert first.status_code == 200
        second = await client.get("/api/auth/demo")
        assert second.status_code == 429
        assert second.json()["detail"] == "公开演示访问过于频繁，请稍后再试"
    audit_rows = _read_jsonl(audit_path)
    assert any(row["event"] == "demo_rate_limited" and row.get("bucket") == "demo-auth" for row in audit_rows)


async def test_public_demo_pipeline_rate_limited(migrated_pg_url: str, tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("JETLINKS_AI_DB_URL", migrated_pg_url)
    monkeypatch.setenv("JETLINKS_AI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JETLINKS_AI_OUTPUTS_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("JETLINKS_AI_JWT_SECRET", "test-jwt-secret-0123456789abcdef0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("JETLINKS_AI_PUBLIC_DEMO_ENABLED", "1")
    monkeypatch.setenv("JETLINKS_AI_PUBLIC_DEMO_PIPELINE_MAX_REQUESTS", "1")
    monkeypatch.setenv("JETLINKS_AI_PUBLIC_DEMO_PIPELINE_WINDOW_SECONDS", "300")

    from jetlinks_ai_api.app_factory import create_app
    from jetlinks_ai_api.config import load_settings

    app = create_app(load_settings())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        demo_resp = await client.get("/api/auth/demo")
        token = demo_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        first = await client.post(
            "/api/skills/pipeline/content",
            headers=headers,
            json={
                "deployment_mode": "hybrid",
                "topic": "Demo 限流测试",
                "audience": "访客",
                "tone": "专业",
                "key_points": ["频率限制"],
            },
        )
        assert first.status_code == 200

        second = await client.post(
            "/api/skills/pipeline/content",
            headers=headers,
            json={
                "deployment_mode": "hybrid",
                "topic": "Demo 限流测试",
                "audience": "访客",
                "tone": "专业",
                "key_points": ["频率限制"],
            },
        )
        assert second.status_code == 429
        assert second.json()["detail"] == "公开演示访问过于频繁，请稍后再试"
