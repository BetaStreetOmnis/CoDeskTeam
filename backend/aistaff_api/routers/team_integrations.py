from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import fetchall, fetchone, row_to_dict, rows_to_dicts, utc_now_iso
from ..deps import CurrentUser, get_current_user, get_db, require_team_admin


router = APIRouter(tags=["team"])


def _token_hint(token: str) -> str:
    t = (token or "").strip()
    if len(t) <= 12:
        return t
    return f"{t[:6]}…{t[-4:]}"


class IntegrationTokenItem(BaseModel):
    id: int
    team_id: int
    kind: str
    name: str
    token_hint: str
    created_by: int | None
    created_at: str
    revoked_at: str | None


class CreateOpenclawIntegrationRequest(BaseModel):
    name: str = Field(default="openclaw-gateway", max_length=80)


class IntegrationTokenCreated(IntegrationTokenItem):
    token: str


@router.get("/team/integrations", response_model=list[IntegrationTokenItem])
async def list_team_integrations(
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> list[IntegrationTokenItem]:
    require_team_admin(user)
    rows = await fetchall(
        db,
        """
        SELECT id, team_id, kind, name, token, created_by, created_at, revoked_at
        FROM integration_tokens
        WHERE team_id = ?
        ORDER BY id DESC
        LIMIT 200
        """,
        (int(user.team_id),),
    )
    out: list[IntegrationTokenItem] = []
    for r in rows_to_dicts(list(rows)):
        out.append(
            IntegrationTokenItem(
                id=int(r["id"]),
                team_id=int(r["team_id"]),
                kind=str(r.get("kind") or ""),
                name=str(r.get("name") or ""),
                token_hint=_token_hint(str(r.get("token") or "")),
                created_by=int(r["created_by"]) if r.get("created_by") is not None else None,
                created_at=str(r.get("created_at") or ""),
                revoked_at=str(r.get("revoked_at") or "") or None,
            )
        )
    return out


@router.post("/team/integrations/openclaw", response_model=IntegrationTokenCreated)
async def create_openclaw_integration_token(
    req: CreateOpenclawIntegrationRequest,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> IntegrationTokenCreated:
    require_team_admin(user)

    token: str | None = None
    for _ in range(6):
        candidate = secrets.token_urlsafe(24)
        existing = await fetchone(db, "SELECT id FROM integration_tokens WHERE token = ?", (candidate,))
        if not row_to_dict(existing):
            token = candidate
            break
    if not token:
        raise HTTPException(status_code=500, detail="生成 token 失败")

    now = utc_now_iso()
    cur = await db.execute(
        """
        INSERT INTO integration_tokens(team_id, kind, name, token, created_by, created_at, revoked_at)
        VALUES (?, ?, ?, ?, ?, ?, NULL)
        """,
        (int(user.team_id), "openclaw", str(req.name or "openclaw-gateway").strip(), token, int(user.id), now),
    )
    token_id = int(cur.lastrowid or 0)
    await db.commit()

    row = await fetchone(
        db,
        """
        SELECT id, team_id, kind, name, token, created_by, created_at, revoked_at
        FROM integration_tokens
        WHERE id = ? AND team_id = ?
        """,
        (token_id, int(user.team_id)),
    )
    data = row_to_dict(row)
    if not data:
        raise HTTPException(status_code=500, detail="创建 token 失败")

    tok = str(data.get("token") or "")
    return IntegrationTokenCreated(
        id=int(data["id"]),
        team_id=int(data["team_id"]),
        kind=str(data.get("kind") or ""),
        name=str(data.get("name") or ""),
        token=tok,
        token_hint=_token_hint(tok),
        created_by=int(data["created_by"]) if data.get("created_by") is not None else None,
        created_at=str(data.get("created_at") or ""),
        revoked_at=str(data.get("revoked_at") or "") or None,
    )


@router.delete("/team/integrations/{token_id}")
async def revoke_team_integration_token(
    token_id: int,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    require_team_admin(user)
    row = await fetchone(
        db,
        "SELECT id, team_id, revoked_at FROM integration_tokens WHERE id = ?",
        (int(token_id),),
    )
    data = row_to_dict(row)
    if not data or int(data.get("team_id") or 0) != int(user.team_id):
        raise HTTPException(status_code=404, detail="token 不存在")

    if str(data.get("revoked_at") or "").strip():
        return {"ok": True}

    now = utc_now_iso()
    await db.execute(
        "UPDATE integration_tokens SET revoked_at = ? WHERE id = ? AND team_id = ?",
        (now, int(token_id), int(user.team_id)),
    )
    await db.commit()
    return {"ok": True}

