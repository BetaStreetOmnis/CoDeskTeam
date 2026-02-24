from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import fetchall, fetchone, row_to_dict, rows_to_dicts, utc_now_iso
from ..deps import CurrentUser, get_current_user, get_db, require_team_admin


router = APIRouter(tags=["team"])


class TeamRequirementDelivery(BaseModel):
    to_team_id: int
    from_team_id: int
    from_team_name: str | None = None
    by_user_id: int | None = None
    by_user_name: str | None = None
    state: str = Field(pattern=r"^(pending|accepted|rejected)$")
    decided_by_user_id: int | None = None
    decided_by_user_name: str | None = None
    decided_at: str | None = None


class TeamRequirement(BaseModel):
    id: int
    team_id: int
    project_id: int | None
    source_team: str
    title: str
    description: str
    status: str
    priority: str
    delivery: TeamRequirementDelivery | None = None
    created_at: str
    updated_at: str


class CreateTeamRequirementDeliveryRequest(BaseModel):
    target_team_id: int = Field(ge=1)


class CreateTeamRequirementRequest(BaseModel):
    project_id: int | None = Field(default=None, ge=0)
    source_team: str = Field(default="", max_length=80)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=20_000)
    status: str = Field(default="incoming", pattern=r"^(incoming|todo|in_progress|done|blocked)$")
    priority: str = Field(default="medium", pattern=r"^(low|medium|high|urgent)$")
    delivery: CreateTeamRequirementDeliveryRequest | None = None


class UpdateTeamRequirementRequest(BaseModel):
    project_id: int | None = Field(default=None, ge=0)
    source_team: str | None = Field(default=None, max_length=80)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=20_000)
    status: str | None = Field(default=None, pattern=r"^(incoming|todo|in_progress|done|blocked)$")
    priority: str | None = Field(default=None, pattern=r"^(low|medium|high|urgent)$")


async def _resolve_team_requirement_project_id(db, team_id: int, project_id: int | None) -> int | None:  # noqa: ANN001
    if project_id is None or int(project_id) <= 0:
        return None
    row = await fetchone(
        db,
        "SELECT id, team_id FROM team_projects WHERE id = ?",
        (int(project_id),),
    )
    data = row_to_dict(row)
    if not data or int(data.get("team_id") or 0) != int(team_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    return int(project_id)


def _build_requirement_delivery(data: dict) -> TeamRequirementDelivery | None:
    from_team_id_raw = data.get("delivery_from_team_id")
    if from_team_id_raw is None:
        return None
    try:
        from_team_id = int(from_team_id_raw)
    except Exception:
        return None
    if from_team_id <= 0:
        return None

    state = str(data.get("delivery_state") or "").strip() or "pending"
    to_team_id = int(data.get("team_id") or 0)

    by_user_id = data.get("delivery_by_user_id")
    decided_by_user_id = data.get("delivery_decided_by_user_id")
    decided_at = data.get("delivery_decided_at")

    return TeamRequirementDelivery(
        to_team_id=to_team_id,
        from_team_id=from_team_id,
        from_team_name=(str(data.get("delivery_from_team_name")).strip() if data.get("delivery_from_team_name") else None),
        by_user_id=int(by_user_id) if by_user_id is not None else None,
        by_user_name=(str(data.get("delivery_by_user_name")).strip() if data.get("delivery_by_user_name") else None),
        state=state,
        decided_by_user_id=int(decided_by_user_id) if decided_by_user_id is not None else None,
        decided_by_user_name=(
            str(data.get("delivery_decided_by_user_name")).strip() if data.get("delivery_decided_by_user_name") else None
        ),
        decided_at=str(decided_at) if decided_at else None,
    )


def _row_to_requirement(data: dict) -> TeamRequirement:
    payload = dict(data)
    payload["delivery"] = _build_requirement_delivery(data)
    return TeamRequirement(**payload)


@router.get("/team/requirements", response_model=list[TeamRequirement])
async def list_team_requirements(
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> list[TeamRequirement]:
    rows = await fetchall(
        db,
        """
        SELECT
          r.id, r.team_id, r.project_id, r.source_team, r.title, r.description, r.status, r.priority,
          r.delivery_from_team_id,
          tf.name AS delivery_from_team_name,
          r.delivery_by_user_id,
          ub.name AS delivery_by_user_name,
          r.delivery_state,
          r.delivery_decided_by_user_id,
          ud.name AS delivery_decided_by_user_name,
          r.delivery_decided_at,
          r.created_at, r.updated_at
        FROM team_requirements r
        LEFT JOIN teams tf ON tf.id = r.delivery_from_team_id
        LEFT JOIN users ub ON ub.id = r.delivery_by_user_id
        LEFT JOIN users ud ON ud.id = r.delivery_decided_by_user_id
        WHERE r.team_id = ?
          AND (r.delivery_state IS NULL OR r.delivery_state <> 'rejected')
        ORDER BY r.updated_at DESC, r.id DESC
        """,
        (user.team_id,),
    )
    return [_row_to_requirement(r) for r in rows_to_dicts(list(rows))]


@router.post("/team/requirements", response_model=TeamRequirement)
async def create_team_requirement(
    req: CreateTeamRequirementRequest,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> TeamRequirement:
    require_team_admin(user)

    now = utc_now_iso()

    target_team_id = req.delivery.target_team_id if req.delivery else None
    is_delivery = bool(target_team_id and int(target_team_id) != int(user.team_id))
    insert_team_id = int(target_team_id) if is_delivery else int(user.team_id)

    if is_delivery:
        target_row = await fetchone(db, "SELECT id FROM teams WHERE id = ?", (insert_team_id,))
        if not row_to_dict(target_row):
            raise HTTPException(status_code=404, detail="目标团队不存在")

    project_id = await _resolve_team_requirement_project_id(db, insert_team_id, req.project_id)

    source_team = user.team_name if is_delivery else req.source_team.strip()
    status = "incoming" if is_delivery else req.status
    delivery_from_team_id = int(user.team_id) if is_delivery else None
    delivery_by_user_id = int(user.id) if is_delivery else None
    delivery_state = "pending" if is_delivery else ""

    cur = await db.execute(
        """
        INSERT INTO team_requirements(
          team_id, project_id, source_team, title, description, status, priority,
          delivery_from_team_id, delivery_by_user_id, delivery_state, delivery_decided_by_user_id, delivery_decided_at,
          created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            insert_team_id,
            project_id,
            source_team,
            req.title.strip(),
            req.description.strip(),
            status,
            req.priority,
            delivery_from_team_id,
            delivery_by_user_id,
            delivery_state,
            None,
            None,
            now,
            now,
        ),
    )
    requirement_id = int(cur.lastrowid)
    await db.commit()

    row = await fetchone(
        db,
        """
        SELECT
          r.id, r.team_id, r.project_id, r.source_team, r.title, r.description, r.status, r.priority,
          r.delivery_from_team_id,
          tf.name AS delivery_from_team_name,
          r.delivery_by_user_id,
          ub.name AS delivery_by_user_name,
          r.delivery_state,
          r.delivery_decided_by_user_id,
          ud.name AS delivery_decided_by_user_name,
          r.delivery_decided_at,
          r.created_at, r.updated_at
        FROM team_requirements r
        LEFT JOIN teams tf ON tf.id = r.delivery_from_team_id
        LEFT JOIN users ub ON ub.id = r.delivery_by_user_id
        LEFT JOIN users ud ON ud.id = r.delivery_decided_by_user_id
        WHERE r.id = ?
        """,
        (requirement_id,),
    )
    data = row_to_dict(row)
    if not data:
        raise HTTPException(status_code=500, detail="创建需求失败")
    return _row_to_requirement(data)


@router.put("/team/requirements/{requirement_id}", response_model=TeamRequirement)
async def update_team_requirement(
    requirement_id: int,
    req: UpdateTeamRequirementRequest,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> TeamRequirement:
    require_team_admin(user)

    existing_row = await fetchone(
        db,
        "SELECT id, team_id FROM team_requirements WHERE id = ?",
        (int(requirement_id),),
    )
    existing = row_to_dict(existing_row)
    if not existing or int(existing.get("team_id") or 0) != user.team_id:
        raise HTTPException(status_code=404, detail="需求不存在")

    fields: list[str] = []
    values: list = []
    if "project_id" in req.model_fields_set:
        fields.append("project_id = ?")
        values.append(await _resolve_team_requirement_project_id(db, user.team_id, req.project_id))
    if req.source_team is not None:
        fields.append("source_team = ?")
        values.append(req.source_team.strip())
    if req.title is not None:
        fields.append("title = ?")
        values.append(req.title.strip())
    if req.description is not None:
        fields.append("description = ?")
        values.append(req.description.strip())
    if req.status is not None:
        fields.append("status = ?")
        values.append(req.status)
    if req.priority is not None:
        fields.append("priority = ?")
        values.append(req.priority)

    if fields:
        fields.append("updated_at = ?")
        values.append(utc_now_iso())
        values.append(int(requirement_id))
        await db.execute(f"UPDATE team_requirements SET {', '.join(fields)} WHERE id = ?", tuple(values))
        await db.commit()

    row = await fetchone(
        db,
        """
        SELECT
          r.id, r.team_id, r.project_id, r.source_team, r.title, r.description, r.status, r.priority,
          r.delivery_from_team_id,
          tf.name AS delivery_from_team_name,
          r.delivery_by_user_id,
          ub.name AS delivery_by_user_name,
          r.delivery_state,
          r.delivery_decided_by_user_id,
          ud.name AS delivery_decided_by_user_name,
          r.delivery_decided_at,
          r.created_at, r.updated_at
        FROM team_requirements r
        LEFT JOIN teams tf ON tf.id = r.delivery_from_team_id
        LEFT JOIN users ub ON ub.id = r.delivery_by_user_id
        LEFT JOIN users ud ON ud.id = r.delivery_decided_by_user_id
        WHERE r.id = ?
        """,
        (int(requirement_id),),
    )
    data = row_to_dict(row)
    if not data:
        raise HTTPException(status_code=404, detail="需求不存在")
    return _row_to_requirement(data)


@router.delete("/team/requirements/{requirement_id}")
async def delete_team_requirement(
    requirement_id: int,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    require_team_admin(user)

    existing_row = await fetchone(
        db,
        "SELECT id, team_id FROM team_requirements WHERE id = ?",
        (int(requirement_id),),
    )
    existing = row_to_dict(existing_row)
    if not existing or int(existing.get("team_id") or 0) != user.team_id:
        raise HTTPException(status_code=404, detail="需求不存在")

    await db.execute("DELETE FROM team_requirements WHERE id = ?", (int(requirement_id),))
    await db.commit()
    return {"ok": True}


@router.post("/team/requirements/{requirement_id}/accept", response_model=TeamRequirement)
async def accept_team_requirement_delivery(
    requirement_id: int,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> TeamRequirement:
    require_team_admin(user)

    existing_row = await fetchone(
        db,
        """
        SELECT id, team_id, status, delivery_from_team_id, delivery_state
        FROM team_requirements
        WHERE id = ?
        """,
        (int(requirement_id),),
    )
    existing = row_to_dict(existing_row)
    if not existing or int(existing.get("team_id") or 0) != user.team_id:
        raise HTTPException(status_code=404, detail="需求不存在")

    from_team_id = int(existing.get("delivery_from_team_id") or 0)
    if from_team_id <= 0:
        raise HTTPException(status_code=400, detail="该需求不是外部交付")

    state = str(existing.get("delivery_state") or "").strip() or "pending"
    if state != "pending":
        raise HTTPException(status_code=400, detail="该交付已处理")

    now = utc_now_iso()
    next_status = "todo" if str(existing.get("status") or "").strip() == "incoming" else str(existing.get("status") or "todo")

    await db.execute(
        """
        UPDATE team_requirements
        SET delivery_state = ?, delivery_decided_by_user_id = ?, delivery_decided_at = ?, status = ?, updated_at = ?
        WHERE id = ?
        """,
        ("accepted", int(user.id), now, next_status, now, int(requirement_id)),
    )
    await db.commit()

    row = await fetchone(
        db,
        """
        SELECT
          r.id, r.team_id, r.project_id, r.source_team, r.title, r.description, r.status, r.priority,
          r.delivery_from_team_id,
          tf.name AS delivery_from_team_name,
          r.delivery_by_user_id,
          ub.name AS delivery_by_user_name,
          r.delivery_state,
          r.delivery_decided_by_user_id,
          ud.name AS delivery_decided_by_user_name,
          r.delivery_decided_at,
          r.created_at, r.updated_at
        FROM team_requirements r
        LEFT JOIN teams tf ON tf.id = r.delivery_from_team_id
        LEFT JOIN users ub ON ub.id = r.delivery_by_user_id
        LEFT JOIN users ud ON ud.id = r.delivery_decided_by_user_id
        WHERE r.id = ?
        """,
        (int(requirement_id),),
    )
    data = row_to_dict(row)
    if not data:
        raise HTTPException(status_code=404, detail="需求不存在")
    return _row_to_requirement(data)


@router.post("/team/requirements/{requirement_id}/reject")
async def reject_team_requirement_delivery(
    requirement_id: int,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    require_team_admin(user)

    existing_row = await fetchone(
        db,
        """
        SELECT id, team_id, delivery_from_team_id, delivery_state
        FROM team_requirements
        WHERE id = ?
        """,
        (int(requirement_id),),
    )
    existing = row_to_dict(existing_row)
    if not existing or int(existing.get("team_id") or 0) != user.team_id:
        raise HTTPException(status_code=404, detail="需求不存在")

    from_team_id = int(existing.get("delivery_from_team_id") or 0)
    if from_team_id <= 0:
        raise HTTPException(status_code=400, detail="该需求不是外部交付")

    state = str(existing.get("delivery_state") or "").strip() or "pending"
    if state != "pending":
        raise HTTPException(status_code=400, detail="该交付已处理")

    now = utc_now_iso()
    await db.execute(
        """
        UPDATE team_requirements
        SET delivery_state = ?, delivery_decided_by_user_id = ?, delivery_decided_at = ?, updated_at = ?
        WHERE id = ?
        """,
        ("rejected", int(user.id), now, now, int(requirement_id)),
    )
    await db.commit()
    return {"ok": True}
