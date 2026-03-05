from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import fetchall, fetchone, row_to_dict, rows_to_dicts, utc_now_iso
from ..deps import CurrentUser, get_current_user, get_db, get_settings, require_team_admin
from ..services.openclaw_admin_service import OpenClawAdminService


router = APIRouter(tags=["team"])


class OpenClawStatusResponse(BaseModel):
    enabled: bool
    embedded: bool
    cli_available: bool
    cli_path: str | None = None
    gateway_base_url: str
    gateway_port: int
    gateway_bind: str
    workdir: str
    gateway_status_json: dict[str, Any] | list[Any] | None = None
    health_json: dict[str, Any] | list[Any] | None = None
    probe: dict[str, Any]
    channels_count: int = 0
    plugins_count: int = 0


class OpenClawChannelItem(BaseModel):
    id: int
    team_id: int
    channel_key: str
    channel_type: str
    external_id: str
    name: str
    enabled: bool
    meta_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class UpsertOpenClawChannelRequest(BaseModel):
    channel_type: str = ""
    external_id: str = ""
    name: str = ""
    enabled: bool = True
    meta_json: dict[str, Any] = Field(default_factory=dict)


class OpenClawPluginItem(BaseModel):
    id: int
    team_id: int
    plugin_key: str
    name: str
    version: str
    source: str
    enabled: bool
    meta_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class UpsertOpenClawPluginRequest(BaseModel):
    name: str = ""
    version: str = ""
    source: str = ""
    enabled: bool = True
    meta_json: dict[str, Any] = Field(default_factory=dict)


class OpenClawSyncResponse(BaseModel):
    channels_upserted: int
    plugins_upserted: int


def _safe_json_load(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            obj = json.loads(value)
        except Exception:
            return {}
        return obj if isinstance(obj, dict) else {}
    return {}


@router.get("/team/openclaw/status", response_model=OpenClawStatusResponse)
async def get_team_openclaw_status(
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> OpenClawStatusResponse:
    require_team_admin(user)
    svc = OpenClawAdminService(settings)
    status = await svc.gateway_status()

    row_channels = await fetchone(
        db,
        "SELECT COUNT(1) AS c FROM openclaw_channels WHERE team_id = ?",
        (int(user.team_id),),
    )
    row_plugins = await fetchone(
        db,
        "SELECT COUNT(1) AS c FROM openclaw_plugins WHERE team_id = ?",
        (int(user.team_id),),
    )
    channels_count = int((row_to_dict(row_channels) or {}).get("c") or 0)
    plugins_count = int((row_to_dict(row_plugins) or {}).get("c") or 0)
    return OpenClawStatusResponse(
        enabled=bool(status.get("enabled")),
        embedded=bool(status.get("embedded")),
        cli_available=bool(status.get("cli_available")),
        cli_path=str(status.get("cli_path") or "") or None,
        gateway_base_url=str(status.get("gateway_base_url") or ""),
        gateway_port=int(status.get("gateway_port") or 0),
        gateway_bind=str(status.get("gateway_bind") or ""),
        workdir=str(status.get("workdir") or ""),
        gateway_status_json=status.get("gateway_status_json"),
        health_json=status.get("health_json"),
        probe=status.get("probe") if isinstance(status.get("probe"), dict) else {},
        channels_count=channels_count,
        plugins_count=plugins_count,
    )


@router.post("/team/openclaw/sync", response_model=OpenClawSyncResponse)
async def sync_team_openclaw(
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> OpenClawSyncResponse:
    require_team_admin(user)
    svc = OpenClawAdminService(settings)
    channels = await svc.discover_channels()
    plugins = await svc.discover_plugins()
    now = utc_now_iso()
    upsert_channels = 0
    upsert_plugins = 0

    for c in channels:
        key = str(c.get("channel_key") or "").strip()
        if not key:
            continue
        await db.execute(
            """
            INSERT INTO openclaw_channels(
              team_id, channel_key, channel_type, external_id, name, enabled, meta_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id, channel_key) DO UPDATE SET
              channel_type = excluded.channel_type,
              external_id = excluded.external_id,
              name = excluded.name,
              enabled = excluded.enabled,
              meta_json = excluded.meta_json,
              updated_at = excluded.updated_at
            """,
            (
                int(user.team_id),
                key,
                str(c.get("channel_type") or "").strip(),
                str(c.get("external_id") or "").strip(),
                str(c.get("name") or key).strip() or key,
                1 if bool(c.get("enabled", True)) else 0,
                json.dumps(c.get("meta") if isinstance(c.get("meta"), dict) else {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        upsert_channels += 1

    for p in plugins:
        key = str(p.get("plugin_key") or "").strip()
        if not key:
            continue
        await db.execute(
            """
            INSERT INTO openclaw_plugins(
              team_id, plugin_key, name, version, source, enabled, meta_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id, plugin_key) DO UPDATE SET
              name = excluded.name,
              version = excluded.version,
              source = excluded.source,
              enabled = excluded.enabled,
              meta_json = excluded.meta_json,
              updated_at = excluded.updated_at
            """,
            (
                int(user.team_id),
                key,
                str(p.get("name") or key).strip() or key,
                str(p.get("version") or "").strip(),
                str(p.get("source") or "").strip(),
                1 if bool(p.get("enabled", True)) else 0,
                json.dumps(p.get("meta") if isinstance(p.get("meta"), dict) else {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        upsert_plugins += 1

    await db.commit()
    return OpenClawSyncResponse(channels_upserted=upsert_channels, plugins_upserted=upsert_plugins)


@router.get("/team/openclaw/channels", response_model=list[OpenClawChannelItem])
async def list_team_openclaw_channels(
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> list[OpenClawChannelItem]:
    require_team_admin(user)
    rows = await fetchall(
        db,
        """
        SELECT id, team_id, channel_key, channel_type, external_id, name, enabled, meta_json, created_at, updated_at
        FROM openclaw_channels
        WHERE team_id = ?
        ORDER BY channel_key ASC
        """,
        (int(user.team_id),),
    )
    out: list[OpenClawChannelItem] = []
    for item in rows_to_dicts(list(rows)):
        out.append(
            OpenClawChannelItem(
                id=int(item.get("id") or 0),
                team_id=int(item.get("team_id") or 0),
                channel_key=str(item.get("channel_key") or ""),
                channel_type=str(item.get("channel_type") or ""),
                external_id=str(item.get("external_id") or ""),
                name=str(item.get("name") or ""),
                enabled=bool(item.get("enabled")),
                meta_json=_safe_json_load(item.get("meta_json")),
                created_at=str(item.get("created_at") or ""),
                updated_at=str(item.get("updated_at") or ""),
            )
        )
    return out


@router.put("/team/openclaw/channels/{channel_key}", response_model=OpenClawChannelItem)
async def upsert_team_openclaw_channel(
    channel_key: str,
    req: UpsertOpenClawChannelRequest,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> OpenClawChannelItem:
    require_team_admin(user)
    key = (channel_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="channel_key 不能为空")

    now = utc_now_iso()
    await db.execute(
        """
        INSERT INTO openclaw_channels(
          team_id, channel_key, channel_type, external_id, name, enabled, meta_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(team_id, channel_key) DO UPDATE SET
          channel_type = excluded.channel_type,
          external_id = excluded.external_id,
          name = excluded.name,
          enabled = excluded.enabled,
          meta_json = excluded.meta_json,
          updated_at = excluded.updated_at
        """,
        (
            int(user.team_id),
            key,
            str(req.channel_type or "").strip(),
            str(req.external_id or "").strip(),
            str(req.name or key).strip() or key,
            1 if req.enabled else 0,
            json.dumps(req.meta_json or {}, ensure_ascii=False),
            now,
            now,
        ),
    )
    await db.commit()

    row = await fetchone(
        db,
        """
        SELECT id, team_id, channel_key, channel_type, external_id, name, enabled, meta_json, created_at, updated_at
        FROM openclaw_channels
        WHERE team_id = ? AND channel_key = ?
        """,
        (int(user.team_id), key),
    )
    data = row_to_dict(row) or {}
    return OpenClawChannelItem(
        id=int(data.get("id") or 0),
        team_id=int(data.get("team_id") or 0),
        channel_key=str(data.get("channel_key") or ""),
        channel_type=str(data.get("channel_type") or ""),
        external_id=str(data.get("external_id") or ""),
        name=str(data.get("name") or ""),
        enabled=bool(data.get("enabled")),
        meta_json=_safe_json_load(data.get("meta_json")),
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
    )


@router.delete("/team/openclaw/channels/{channel_key}")
async def delete_team_openclaw_channel(
    channel_key: str,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> dict[str, bool]:
    require_team_admin(user)
    key = (channel_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="channel_key 不能为空")
    await db.execute(
        "DELETE FROM openclaw_channels WHERE team_id = ? AND channel_key = ?",
        (int(user.team_id), key),
    )
    await db.commit()
    return {"ok": True}


@router.get("/team/openclaw/plugins", response_model=list[OpenClawPluginItem])
async def list_team_openclaw_plugins(
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> list[OpenClawPluginItem]:
    require_team_admin(user)
    rows = await fetchall(
        db,
        """
        SELECT id, team_id, plugin_key, name, version, source, enabled, meta_json, created_at, updated_at
        FROM openclaw_plugins
        WHERE team_id = ?
        ORDER BY plugin_key ASC
        """,
        (int(user.team_id),),
    )
    out: list[OpenClawPluginItem] = []
    for item in rows_to_dicts(list(rows)):
        out.append(
            OpenClawPluginItem(
                id=int(item.get("id") or 0),
                team_id=int(item.get("team_id") or 0),
                plugin_key=str(item.get("plugin_key") or ""),
                name=str(item.get("name") or ""),
                version=str(item.get("version") or ""),
                source=str(item.get("source") or ""),
                enabled=bool(item.get("enabled")),
                meta_json=_safe_json_load(item.get("meta_json")),
                created_at=str(item.get("created_at") or ""),
                updated_at=str(item.get("updated_at") or ""),
            )
        )
    return out


@router.put("/team/openclaw/plugins/{plugin_key}", response_model=OpenClawPluginItem)
async def upsert_team_openclaw_plugin(
    plugin_key: str,
    req: UpsertOpenClawPluginRequest,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> OpenClawPluginItem:
    require_team_admin(user)
    key = (plugin_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="plugin_key 不能为空")
    now = utc_now_iso()
    await db.execute(
        """
        INSERT INTO openclaw_plugins(
          team_id, plugin_key, name, version, source, enabled, meta_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(team_id, plugin_key) DO UPDATE SET
          name = excluded.name,
          version = excluded.version,
          source = excluded.source,
          enabled = excluded.enabled,
          meta_json = excluded.meta_json,
          updated_at = excluded.updated_at
        """,
        (
            int(user.team_id),
            key,
            str(req.name or key).strip() or key,
            str(req.version or "").strip(),
            str(req.source or "").strip(),
            1 if req.enabled else 0,
            json.dumps(req.meta_json or {}, ensure_ascii=False),
            now,
            now,
        ),
    )
    await db.commit()

    row = await fetchone(
        db,
        """
        SELECT id, team_id, plugin_key, name, version, source, enabled, meta_json, created_at, updated_at
        FROM openclaw_plugins
        WHERE team_id = ? AND plugin_key = ?
        """,
        (int(user.team_id), key),
    )
    data = row_to_dict(row) or {}
    return OpenClawPluginItem(
        id=int(data.get("id") or 0),
        team_id=int(data.get("team_id") or 0),
        plugin_key=str(data.get("plugin_key") or ""),
        name=str(data.get("name") or ""),
        version=str(data.get("version") or ""),
        source=str(data.get("source") or ""),
        enabled=bool(data.get("enabled")),
        meta_json=_safe_json_load(data.get("meta_json")),
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
    )


@router.delete("/team/openclaw/plugins/{plugin_key}")
async def delete_team_openclaw_plugin(
    plugin_key: str,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> dict[str, bool]:
    require_team_admin(user)
    key = (plugin_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="plugin_key 不能为空")
    await db.execute(
        "DELETE FROM openclaw_plugins WHERE team_id = ? AND plugin_key = ?",
        (int(user.team_id), key),
    )
    await db.commit()
    return {"ok": True}

