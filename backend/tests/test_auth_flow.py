from __future__ import annotations

from datetime import datetime, timezone


async def test_health_ok(client) -> None:  # noqa: ANN001
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("ok") is True


async def test_auth_status_setup_required(client) -> None:  # noqa: ANN001
    resp = await client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json() == {"setup_required": True}


async def test_setup_then_me(client) -> None:  # noqa: ANN001
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
    token = setup_resp.json().get("access_token")
    assert token

    me_resp = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["user"]["email"] == "owner@example.com"
    assert body["active_team"]["name"] == "大模型团队"


async def test_register_team_mismatch_is_rejected(client, pg_url: str) -> None:  # noqa: ANN001
    setup_resp = await client.post(
        "/api/auth/setup",
        json={
            "team_name": "项目一部",
            "name": "Owner",
            "email": "owner@example.com",
            "password": "password123",
        },
    )
    assert setup_resp.status_code == 200
    token = setup_resp.json()["access_token"]

    invite_resp = await client.post(
        "/api/team/invites",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": None, "role": "member", "expires_days": 7},
    )
    assert invite_resp.status_code == 200
    invite_token = invite_resp.json()["token"]

    import psycopg

    now = datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()
    with psycopg.connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO teams(name, created_at) VALUES (%s, %s) RETURNING id", ("售前团队", now))
            other_team_id = int(cur.fetchone()[0])
        conn.commit()

    reg_resp = await client.post(
        "/api/auth/register",
        json={
            "invite_token": invite_token,
            "team_id": other_team_id,
            "name": "New User",
            "email": "newuser@example.com",
            "password": "password123",
        },
    )
    assert reg_resp.status_code == 400
    assert reg_resp.json().get("detail") == "邀请码不属于所选团队"

