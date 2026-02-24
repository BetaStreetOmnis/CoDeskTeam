from __future__ import annotations


async def test_openclaw_integration_message_flow(client, pg_url: str) -> None:  # noqa: ANN001
    setup_resp = await client.post(
        "/api/auth/setup",
        json={
            "team_name": "大模型团队",
            "name": "Owner",
            "email": "owner@example.com",
            "password": "password123",
        },
    )
    assert setup_resp.status_code == 200
    owner_token = setup_resp.json()["access_token"]

    create_token_resp = await client.post(
        "/api/team/integrations/openclaw",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "test-openclaw"},
    )
    assert create_token_resp.status_code == 200
    integration_token = create_token_resp.json()["token"]

    msg_resp = await client.post(
        "/api/integrations/openclaw/message",
        headers={"x-jetlinks-ai-integration-token": integration_token},
        json={
            "external_user_id": "whatsapp:+1234567890",
            "external_display_name": "Alice",
            "thread_id": "thread-1",
            "message": "Hello",
            "provider": "mock",
        },
    )
    assert msg_resp.status_code == 200
    data1 = msg_resp.json()
    assert "mock 模型" in data1["assistant"]
    sid1 = data1["session_id"]
    assert sid1.startswith("oc-")

    msg_resp2 = await client.post(
        "/api/integrations/openclaw/message",
        headers={"x-jetlinks-ai-integration-token": integration_token},
        json={
            "external_user_id": "whatsapp:+1234567890",
            "external_display_name": "Alice",
            "thread_id": "thread-1",
            "message": "Hello again",
            "provider": "mock",
        },
    )
    assert msg_resp2.status_code == 200
    data2 = msg_resp2.json()
    assert data2["session_id"] == sid1

    import psycopg

    with psycopg.connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM integration_tokens WHERE kind = 'openclaw'")
            assert int(cur.fetchone()[0]) == 1

            cur.execute("SELECT COUNT(*) FROM external_identities WHERE provider = 'openclaw'")
            assert int(cur.fetchone()[0]) == 1

            cur.execute("SELECT COUNT(*) FROM chat_sessions WHERE session_id = %s", (sid1,))
            assert int(cur.fetchone()[0]) == 1

            cur.execute("SELECT COUNT(*) FROM chat_messages WHERE session_id = %s", (sid1,))
            # 2 turns => 4 messages (user+assistant each)
            assert int(cur.fetchone()[0]) == 4
