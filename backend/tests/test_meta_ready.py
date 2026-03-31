from __future__ import annotations


async def test_ready_reports_db_and_runtime_paths(client) -> None:  # noqa: ANN001
    resp = await client.get("/ready")
    assert resp.status_code == 200

    body = resp.json()
    assert body.get("ok") is True
    assert body.get("db") == "ok"
    assert str(body.get("data_dir") or "").endswith("/data")
    assert str(body.get("outputs_dir") or "").endswith("/outputs")
