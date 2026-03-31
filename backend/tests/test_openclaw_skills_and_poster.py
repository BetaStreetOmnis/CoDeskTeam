from __future__ import annotations


async def _setup_token(client) -> str:  # noqa: ANN001
    resp = await client.post(
        "/api/auth/setup",
        json={
            "team_name": "OpenClaw Team",
            "name": "Owner",
            "email": "owner@example.com",
            "password": "password123",
        },
    )
    assert resp.status_code == 200
    token = str(resp.json().get("access_token") or "")
    assert token
    return token


async def test_openclaw_skill_crud(client) -> None:  # noqa: ANN001
    token = await _setup_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    put_resp = await client.put(
        "/api/team/openclaw/skills/poster.generate",
        headers=headers,
        json={
            "name": "海报生成",
            "description": "生成大图海报",
            "entrypoint": "poster.generate",
            "enabled": True,
            "meta_json": {"category": "design"},
        },
    )
    assert put_resp.status_code == 200
    body = put_resp.json()
    assert body["skill_key"] == "poster.generate"
    assert body["entrypoint"] == "poster.generate"

    list_resp = await client.get("/api/team/openclaw/skills", headers=headers)
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "海报生成"

    status_resp = await client.get("/api/team/openclaw/status", headers=headers)
    assert status_resp.status_code == 200
    assert int(status_resp.json().get("skills_count") or 0) == 1

    del_resp = await client.delete("/api/team/openclaw/skills/poster.generate", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json().get("ok") is True


async def test_docs_poster_generates_svg(client) -> None:  # noqa: ANN001
    token = await _setup_token(client)
    resp = await client.post(
        "/api/docs/poster",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "AI 海报",
            "subtitle": "可下载的大图交付物",
            "bullets": ["支持团队协作", "支持工作区落盘", "支持下载链接"],
            "theme": "aurora",
            "width": 1600,
            "height": 2400,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert str(body.get("file_id") or "").endswith(".svg")
    assert body.get("content_type") == "image/svg+xml"
    assert str(body.get("download_url") or "").startswith("/api/files/") or str(body.get("download_url") or "").startswith("http")
