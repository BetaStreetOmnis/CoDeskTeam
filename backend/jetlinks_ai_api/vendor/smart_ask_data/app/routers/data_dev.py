from __future__ import annotations

import random
import sqlite3
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.settings import get_settings
from app.routers.api import _current_user
from app.services.data_dev_store import dev_store


router = APIRouter(tags=["data_dev"])


class TaskCreateRequest(BaseModel):
    name: str = Field(default="未命名任务")
    type: str = Field(default="flink_realtime")
    description: str = Field(default="")
    runtime: dict[str, Any] | None = None
    pipeline: dict[str, Any] | None = None
    linkage: dict[str, Any] | None = None


class TaskPatchRequest(BaseModel):
    name: str | None = None
    type: str | None = None
    description: str | None = None
    status: str | None = None
    runtime: dict[str, Any] | None = None
    pipeline: dict[str, Any] | None = None
    linkage: dict[str, Any] | None = None


class VersionRequest(BaseModel):
    comment: str = Field(default="")


class RollbackRequest(BaseModel):
    version: int


def _simulate_alarm_ingest(db_path: str, *, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    now_ms = int(time.time() * 1000)

    inserted = 0
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 基于现有演示库的单位分布，生成“新到达”的警情记录（用于演示：数据开发→问数联动）
        try:
            cur.execute("SELECT DISTINCT unit_name FROM fire_alarm_record")
            units = [r[0] for r in cur.fetchall() if r and r[0]]
        except Exception:
            units = []

        if not units:
            units = ["广东省某消防救援支队"]

        device_types = ["烟感", "温感", "手报", "喷淋", "水压"]
        locations = [
            "广州市天河区XX大厦",
            "广州市越秀区XX商场",
            "深圳市南山区XX园区",
            "佛山市禅城区XX小区",
            "东莞市南城街道XX写字楼",
            "珠海市香洲区XX学校",
        ]
        guards = ["值班员A", "值班员B", "值班员C", "值班员D"]

        n = rng.randint(6, 12)
        for i in range(n):
            create_time = now_ms - rng.randint(0, 25 * 60 * 1000)
            cur.execute(
                """
                INSERT OR IGNORE INTO fire_alarm_record (
                    id, unit_name, device_name, device_type, alarm_location,
                    processing_state, guard_name, create_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"RT{seed:08x}_{i:02d}",
                    rng.choice(units),
                    f"{rng.choice(['A', 'B', 'C'])}区{rng.choice(['1','2','3'])}层{rng.randint(1,30)}号",
                    rng.choice(device_types),
                    rng.choice(locations),
                    rng.choice(["未处理", "未处理", "处理中"]),
                    rng.choice(guards),
                    create_time,
                ),
            )
            inserted += int(cur.rowcount or 0)

        conn.commit()
        conn.close()
    except Exception:
        inserted = 0

    return {
        "type": "alarm_ingest",
        "inserted": inserted,
        "message": f"已模拟写入 {inserted} 条警情到演示库（回到「智能问数」可立即查询）。" if inserted else "演示库写入失败（可忽略，不影响页面展示）。",
    }


@router.get("/overview")
def overview(request: Request):
    user = _current_user(request)
    dev_store.ensure_seed(user["username"])
    tasks = dev_store.list_tasks(user["username"])
    running = sum(1 for t in tasks if t.get("status") == "running")
    return {"success": True, "data": {"task_total": len(tasks), "running": running}}


@router.get("/sources")
def sources(request: Request):
    _current_user(request)
    return {
        "success": True,
        "data": [
            {
                "id": "alarm_rt",
                "name": "智能接处警系统（警情实时流）",
                "type": "kafka",
                "description": "警情数据秒级接入：接警、派警、处置状态等。",
            },
            {
                "id": "personnel_pos_rt",
                "name": "消防员综合定位系统（人员定位实时流）",
                "type": "kafka",
                "description": "人员定位/GIS轨迹、队站态势，支撑指挥调度。",
            },
            {
                "id": "vehicle_gps_rt",
                "name": "车辆GPS（车辆定位实时流）",
                "type": "kafka",
                "description": "车辆GPS轨迹、速度、方向、出动统计等。",
            },
        ],
    }


@router.get("/tasks")
def list_tasks(request: Request):
    user = _current_user(request)
    dev_store.ensure_seed(user["username"])
    return {"success": True, "data": dev_store.list_tasks(user["username"])}


@router.post("/tasks")
def create_task(request: Request, payload: TaskCreateRequest):
    user = _current_user(request)
    dev_store.ensure_seed(user["username"])
    task = dev_store.create_task(user["username"], payload.model_dump())
    return {"success": True, "data": task}


@router.get("/tasks/{task_id}")
def get_task(request: Request, task_id: str):
    user = _current_user(request)
    dev_store.ensure_seed(user["username"])
    task = dev_store.get_task(user["username"], task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "data": task}


@router.patch("/tasks/{task_id}")
def patch_task(request: Request, task_id: str, payload: TaskPatchRequest):
    user = _current_user(request)
    dev_store.ensure_seed(user["username"])
    task = dev_store.update_task(user["username"], task_id, payload.model_dump(exclude_unset=True))
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "data": task}


@router.post("/tasks/{task_id}/versions")
def add_version(request: Request, task_id: str, payload: VersionRequest):
    user = _current_user(request)
    dev_store.ensure_seed(user["username"])
    task = dev_store.add_version(user["username"], task_id, payload.comment)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "data": task}


@router.post("/tasks/{task_id}/rollback")
def rollback(request: Request, task_id: str, payload: RollbackRequest):
    user = _current_user(request)
    dev_store.ensure_seed(user["username"])
    task = dev_store.rollback(user["username"], task_id, payload.version)
    if not task:
        raise HTTPException(status_code=404, detail="找不到指定版本")
    return {"success": True, "data": task}


@router.post("/tasks/{task_id}/runs")
def start_run(request: Request, task_id: str):
    user = _current_user(request)
    settings = get_settings()
    dev_store.ensure_seed(user["username"])
    run = dev_store.create_run(user["username"], task_id)
    if not run:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = dev_store.get_task(user["username"], task_id) or {}
    effects: list[dict[str, Any]] = []
    if "警情" in str(task.get("name") or ""):
        effects.append(_simulate_alarm_ingest(settings.demo_db_path, seed=int(str(run.get("id") or "0")[:8], 16)))

    return {"success": True, "data": {"run_id": run["id"], "effects": effects}}


@router.get("/tasks/{task_id}/runs")
def list_runs(request: Request, task_id: str):
    user = _current_user(request)
    dev_store.ensure_seed(user["username"])
    return {"success": True, "data": dev_store.list_runs(user["username"], task_id)}


@router.get("/runs/{run_id}")
def get_run(request: Request, run_id: str):
    user = _current_user(request)
    dev_store.ensure_seed(user["username"])
    view = dev_store.get_run(user["username"], run_id)
    if not view:
        raise HTTPException(status_code=404, detail="运行实例不存在")
    return {"success": True, "data": {"run": view.run, "logs": view.logs, "finished": view.finished}}


@router.post("/simulate/linkage")
def simulate_linkage(request: Request):
    user = _current_user(request)
    settings = get_settings()

    alarm: dict[str, Any] | None = None
    forces: list[dict[str, Any]] = []
    equipment: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(settings.demo_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT unit_name, alarm_location, processing_state, datetime(create_time/1000,'unixepoch','localtime') AS alarm_time "
            "FROM fire_alarm_record ORDER BY create_time DESC LIMIT 1"
        )
        r = cur.fetchone()
        if r:
            alarm = {k: r[k] for k in r.keys()}

        cur.execute("SELECT station, COUNT(*) AS personnel_count FROM fire_personnel GROUP BY station ORDER BY personnel_count DESC")
        forces = [{k: row[k] for k in row.keys()} for row in cur.fetchall()]

        cur.execute(
            "SELECT station, SUM(quantity) AS in_stock_qty "
            "FROM fire_equipment WHERE status = '在库' GROUP BY station ORDER BY in_stock_qty DESC"
        )
        equipment = [{k: row[k] for k in row.keys()} for row in cur.fetchall()]
        conn.close()
    except Exception:
        alarm = None

    # 演示：选取TOP2救援力量与TOP2装备库存站点作为推荐
    recommended_forces = forces[:2]
    recommended_equipment = equipment[:2]

    return {
        "success": True,
        "data": {
            "trigger": "警情触发",
            "alarm": alarm
            or {
                "unit_name": "广东省某重点单位",
                "alarm_location": "XX区XX路XX号",
                "processing_state": "未处理",
                "alarm_time": "2026-01-12 14:30:00",
            },
            "push_targets": [
                {"system": "智能指挥系统", "channel": "指挥大屏", "status": "已推送"},
                {"system": "装备物资管理系统", "channel": "装备库存", "status": "已同步"},
                {"system": "综合定位系统", "channel": "周边救援力量", "status": "已推送"},
            ],
            "recommended_forces": recommended_forces,
            "recommended_equipment": recommended_equipment,
            "operator": {"username": user["username"], "role": user["role"]},
        },
    }


@router.post("/reset")
def reset_dev(request: Request):
    user = _current_user(request)
    dev_store.reset_user(user["username"])
    dev_store.ensure_seed(user["username"])
    return {"success": True}
