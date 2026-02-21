from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4


def _now_ms() -> int:
    return int(time.time() * 1000)


def _default_store_path() -> Path:
    env = os.getenv("SMARTASK_DEV_STORE_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "storage" / "data_dev_store.json"


@dataclass(frozen=True)
class RunView:
    run: dict[str, Any]
    status: str
    progress: float
    logs: list[dict[str, Any]]
    finished: bool


class DataDevStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_store_path()
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {"users": {}}
        self._load()

    def _load(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._save()
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw or "{}")
            if isinstance(data, dict) and "users" in data and isinstance(data["users"], dict):
                self._data = data
        except Exception:
            self._data = {"users": {}}
            self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def _ensure_user(self, user: str) -> dict[str, Any]:
        users = self._data.setdefault("users", {})
        if user not in users:
            users[user] = {"tasks": {}, "runs": {}}
        return users[user]

    def ensure_seed(self, user: str) -> None:
        with self._lock:
            u = self._ensure_user(user)
            tasks: dict[str, Any] = u.setdefault("tasks", {})
            if tasks:
                return

            now = _now_ms()

            def add_task(name: str, task_type: str, description: str, pipeline: dict[str, Any]) -> None:
                task_id = uuid4().hex
                task = {
                    "id": task_id,
                    "name": name,
                    "type": task_type,
                    "description": description,
                    "status": "draft",
                    "version": 1,
                    "created_at": now,
                    "updated_at": now,
                    "runtime": {
                        "parallelism": 4,
                        "checkpoint_interval_ms": 10_000,
                        "restart_strategy": "fixed-delay",
                        "restart_attempts": 3,
                        "restart_delay_ms": 10_000,
                    },
                    "pipeline": pipeline,
                    "linkage": {
                        "enabled": True,
                        "trigger": "警情触发",
                        "rules": [
                            {"name": "推送周边救援力量", "enabled": True},
                            {"name": "同步装备库存到指挥大屏", "enabled": True},
                            {"name": "推送人员定位与车辆GPS", "enabled": True},
                        ],
                    },
                    "versions": [
                        {
                            "version": 1,
                            "created_at": now,
                            "comment": "初始版本（系统预置）",
                            "snapshot": {"runtime": {}, "pipeline": pipeline, "linkage": {}},
                        }
                    ],
                }
                tasks[task_id] = task

            add_task(
                name="警情实时接入（智能接处警系统）",
                task_type="flink_realtime",
                description="秒级接入警情数据，解析/清洗后落地到 ODS，并可联动推送指挥大屏。",
                pipeline={
                    "nodes": [
                        {
                            "id": "src_alarm",
                            "category": "source",
                            "name": "智能接处警系统-警情流",
                            "kind": "kafka_source",
                            "params": {"topic": "alarm_stream", "format": "json", "watermark": "event_time"},
                        },
                        {
                            "id": "t_clean",
                            "category": "transform",
                            "name": "字段清洗/标准化",
                            "kind": "cleanse",
                            "params": {"drop_null": True, "normalize_unit": True},
                        },
                        {
                            "id": "sink_ods",
                            "category": "sink",
                            "name": "ODS_警情明细",
                            "kind": "ods_sink",
                            "params": {"table": "ods_alarm_record", "mode": "upsert"},
                        },
                    ],
                    "edges": [{"source": "src_alarm", "target": "t_clean"}, {"source": "t_clean", "target": "sink_ods"}],
                },
            )

            add_task(
                name="人员定位实时处理（综合定位系统）",
                task_type="flink_realtime",
                description="对接人员定位实时流，进行轨迹清洗与5秒窗口聚合，支撑指挥调度态势展示。",
                pipeline={
                    "nodes": [
                        {
                            "id": "src_pos",
                            "category": "source",
                            "name": "消防员综合定位系统-人员定位流",
                            "kind": "kafka_source",
                            "params": {"topic": "personnel_position", "format": "json"},
                        },
                        {
                            "id": "t_geo",
                            "category": "transform",
                            "name": "轨迹清洗/纠偏",
                            "kind": "geo_cleanse",
                            "params": {"snap_to_road": False, "max_speed_kmh": 140},
                        },
                        {
                            "id": "t_win",
                            "category": "transform",
                            "name": "5秒窗口聚合",
                            "kind": "window_agg",
                            "params": {"window": "5s", "group_by": ["person_id"]},
                        },
                        {
                            "id": "sink_topic",
                            "category": "sink",
                            "name": "DWD_人员定位主题库",
                            "kind": "warehouse_sink",
                            "params": {"table": "dwd_person_position_rt", "partition": "dt"},
                        },
                    ],
                    "edges": [
                        {"source": "src_pos", "target": "t_geo"},
                        {"source": "t_geo", "target": "t_win"},
                        {"source": "t_win", "target": "sink_topic"},
                    ],
                },
            )

            add_task(
                name="车辆GPS实时汇聚（车辆定位/GPS）",
                task_type="flink_realtime",
                description="秒级接入车辆GPS轨迹，生成车辆态势与出动统计指标，支撑应急决策。",
                pipeline={
                    "nodes": [
                        {
                            "id": "src_gps",
                            "category": "source",
                            "name": "车辆GPS-轨迹流",
                            "kind": "kafka_source",
                            "params": {"topic": "vehicle_gps", "format": "json"},
                        },
                        {
                            "id": "t_gps_clean",
                            "category": "transform",
                            "name": "GPS清洗/去噪",
                            "kind": "geo_cleanse",
                            "params": {"snap_to_road": True, "max_speed_kmh": 160},
                        },
                        {
                            "id": "sink_rt",
                            "category": "sink",
                            "name": "DWD_车辆轨迹主题库",
                            "kind": "warehouse_sink",
                            "params": {"table": "dwd_vehicle_gps_rt", "partition": "dt"},
                        },
                    ],
                    "edges": [{"source": "src_gps", "target": "t_gps_clean"}, {"source": "t_gps_clean", "target": "sink_rt"}],
                },
            )

            self._save()

    def reset_user(self, user: str) -> None:
        with self._lock:
            users = self._data.setdefault("users", {})
            users[user] = {"tasks": {}, "runs": {}}
            self._save()

    def list_tasks(self, user: str) -> list[dict[str, Any]]:
        with self._lock:
            u = self._ensure_user(user)
            tasks = list((u.get("tasks") or {}).values())
            tasks.sort(key=lambda t: int(t.get("updated_at") or 0), reverse=True)
            return tasks

    def get_task(self, user: str, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            u = self._ensure_user(user)
            t = (u.get("tasks") or {}).get(task_id)
            return t

    def create_task(self, user: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            u = self._ensure_user(user)
            tasks: dict[str, Any] = u.setdefault("tasks", {})
            now = _now_ms()

            task_id = uuid4().hex
            name = (payload.get("name") or "未命名任务").strip()
            task_type = (payload.get("type") or "flink_realtime").strip()
            description = (payload.get("description") or "").strip()

            task = {
                "id": task_id,
                "name": name,
                "type": task_type,
                "description": description,
                "status": "draft",
                "version": 1,
                "created_at": now,
                "updated_at": now,
                "runtime": payload.get("runtime")
                or {
                    "parallelism": 4,
                    "checkpoint_interval_ms": 10_000,
                    "restart_strategy": "fixed-delay",
                    "restart_attempts": 3,
                    "restart_delay_ms": 10_000,
                },
                "pipeline": payload.get("pipeline") or {"nodes": [], "edges": []},
                "linkage": payload.get("linkage") or {"enabled": True, "trigger": "警情触发", "rules": []},
                "versions": [
                    {
                        "version": 1,
                        "created_at": now,
                        "comment": "初始版本",
                        "snapshot": {
                            "runtime": payload.get("runtime") or {},
                            "pipeline": payload.get("pipeline") or {"nodes": [], "edges": []},
                            "linkage": payload.get("linkage") or {},
                        },
                    }
                ],
            }
            tasks[task_id] = task
            self._save()
            return task

    def update_task(self, user: str, task_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            u = self._ensure_user(user)
            tasks: dict[str, Any] = u.setdefault("tasks", {})
            t = tasks.get(task_id)
            if not t:
                return None

            for key in ("name", "description", "type", "status"):
                if key in patch and patch[key] is not None:
                    t[key] = patch[key]
            for key in ("runtime", "pipeline", "linkage"):
                if key in patch and isinstance(patch[key], dict):
                    t[key] = patch[key]

            t["updated_at"] = _now_ms()
            tasks[task_id] = t
            self._save()
            return t

    def add_version(self, user: str, task_id: str, comment: str) -> dict[str, Any] | None:
        with self._lock:
            u = self._ensure_user(user)
            t = (u.get("tasks") or {}).get(task_id)
            if not t:
                return None

            now = _now_ms()
            version = int(t.get("version") or 1) + 1
            t["version"] = version
            t.setdefault("versions", []).append(
                {
                    "version": version,
                    "created_at": now,
                    "comment": (comment or "").strip() or f"版本 {version}",
                    "snapshot": {"runtime": t.get("runtime") or {}, "pipeline": t.get("pipeline") or {}, "linkage": t.get("linkage") or {}},
                }
            )
            t["updated_at"] = now
            self._save()
            return t

    def rollback(self, user: str, task_id: str, version: int) -> dict[str, Any] | None:
        with self._lock:
            u = self._ensure_user(user)
            t = (u.get("tasks") or {}).get(task_id)
            if not t:
                return None
            versions = list(t.get("versions") or [])
            target = next((v for v in versions if int(v.get("version") or 0) == int(version)), None)
            if not target:
                return None

            snap = target.get("snapshot") or {}
            if isinstance(snap.get("runtime"), dict):
                t["runtime"] = snap["runtime"]
            if isinstance(snap.get("pipeline"), dict):
                t["pipeline"] = snap["pipeline"]
            if isinstance(snap.get("linkage"), dict):
                t["linkage"] = snap["linkage"]

            now = _now_ms()
            t["updated_at"] = now
            t.setdefault("versions", []).append(
                {
                    "version": int(t.get("version") or 1) + 1,
                    "created_at": now,
                    "comment": f"回滚到版本 {version}",
                    "snapshot": {"runtime": t.get("runtime") or {}, "pipeline": t.get("pipeline") or {}, "linkage": t.get("linkage") or {}},
                }
            )
            t["version"] = int(t.get("version") or 1) + 1
            self._save()
            return t

    def create_run(self, user: str, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            u = self._ensure_user(user)
            t = (u.get("tasks") or {}).get(task_id)
            if not t:
                return None

            now = _now_ms()
            run_id = uuid4().hex
            duration_ms = 9_000
            events = [
                {"offset_ms": 0, "level": "INFO", "msg": "提交任务到 Flink 集群..."},
                {"offset_ms": 900, "level": "INFO", "msg": "拉起 JobManager/TaskManager 资源..."},
                {"offset_ms": 1600, "level": "INFO", "msg": "连接实时数据源（Kafka）..."},
                {"offset_ms": 2400, "level": "INFO", "msg": "任务拓扑编译完成，开始处理数据..."},
                {"offset_ms": 4200, "level": "INFO", "msg": "Checkpoint #1 完成"},
                {"offset_ms": 6100, "level": "INFO", "msg": "Checkpoint #2 完成"},
                {"offset_ms": 7800, "level": "INFO", "msg": "处理吞吐稳定，联动规则已生效"},
                {"offset_ms": 9000, "level": "INFO", "msg": "运行完成（演示模式）"},
            ]

            run = {
                "id": run_id,
                "task_id": task_id,
                "task_name": t.get("name"),
                "started_at": now,
                "duration_ms": duration_ms,
                "final_status": "success",
                "events": events,
                "metrics_seed": int(now % 10_000),
            }
            runs: dict[str, Any] = u.setdefault("runs", {})
            runs[run_id] = run

            t["status"] = "running"
            t["updated_at"] = now
            self._save()
            return run

    def list_runs(self, user: str, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            u = self._ensure_user(user)
            raw_runs = [r for r in (u.get("runs") or {}).values() if r.get("task_id") == task_id]
            raw_runs.sort(key=lambda r: int(r.get("started_at") or 0), reverse=True)
            items: list[dict[str, Any]] = []
            for r in raw_runs[:50]:
                view = self._compute_run_view(r)
                items.append(
                    {
                        "id": r.get("id"),
                        "task_id": r.get("task_id"),
                        "task_name": r.get("task_name"),
                        "started_at": r.get("started_at"),
                        "duration_ms": r.get("duration_ms"),
                        "status": view.status,
                        "progress": view.progress,
                    }
                )
            return items

    def _compute_run_view(self, run: dict[str, Any]) -> RunView:
        started_at = int(run.get("started_at") or 0)
        duration_ms = int(run.get("duration_ms") or 1)
        elapsed_ms = max(0, _now_ms() - started_at)
        progress = min(1.0, elapsed_ms / max(1, duration_ms))
        finished = elapsed_ms >= duration_ms
        status = (run.get("final_status") or "success") if finished else "running"

        visible: list[dict[str, Any]] = []
        for e in run.get("events") or []:
            try:
                if int(e.get("offset_ms") or 0) <= elapsed_ms:
                    visible.append({"ts": started_at + int(e.get("offset_ms") or 0), "level": e.get("level"), "msg": e.get("msg")})
            except Exception:
                continue

        base = int(run.get("metrics_seed") or 0)
        metrics = {
            "input_qps": int(1200 + base % 200 + progress * 800),
            "output_qps": int(1100 + base % 150 + progress * 700),
            "latency_ms": int(280 - progress * 140),
            "checkpoint_interval_ms": 10_000,
            "state_size_mb": round(64 + progress * 28, 1),
            "backpressure": round(0.12 + (1.0 - progress) * 0.08, 3),
        }

        run_view = dict(run)
        run_view["status"] = status
        run_view["progress"] = progress
        run_view["metrics"] = metrics
        return RunView(run=run_view, status=status, progress=progress, logs=visible, finished=finished)

    def get_run(self, user: str, run_id: str) -> RunView | None:
        with self._lock:
            u = self._ensure_user(user)
            run = (u.get("runs") or {}).get(run_id)
            if not run:
                return None
            view = self._compute_run_view(run)

            if view.finished:
                tasks: dict[str, Any] = u.setdefault("tasks", {})
                task_id = str(run.get("task_id") or "")
                t = tasks.get(task_id)
                if t and t.get("status") == "running":
                    t["status"] = "success" if view.status == "success" else "failed"
                    t["updated_at"] = _now_ms()
                    tasks[task_id] = t
                    self._save()

            return view


dev_store = DataDevStore()
