from __future__ import annotations

import random
import sqlite3
import time
from pathlib import Path


def ensure_demo_db(db_path: str) -> None:
    """
    Create a small SQLite demo database for out-of-box ChatBI.

    The dataset is intentionally synthetic and non-sensitive.
    """

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    now_ms = int(time.time() * 1000)

    units = [
        "广州市天河区消防救援大队",
        "广州市越秀区消防救援大队",
        "深圳市南山区消防救援大队",
        "深圳市福田区消防救援大队",
        "佛山市禅城区消防救援大队",
        "东莞市南城街道消防救援大队",
    ]
    stations = ["天河站", "越秀站", "南山站", "福田站", "禅城站", "南城站"]
    locations = [
        "广州市天河区体育西路XX号",
        "广州市越秀区中山五路XX号",
        "深圳市南山区科技园XX楼",
        "深圳市福田区会展中心周边",
        "佛山市禅城区季华路XX号",
        "东莞市南城街道鸿福路XX号",
    ]
    device_types = ["烟感", "温感", "手报", "喷淋", "水压"]
    equipment_categories = ["水带", "灭火器", "呼吸器", "破拆工具", "无人机", "对讲机"]

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS fire_alarm_record (
            id TEXT PRIMARY KEY,
            unit_name TEXT,
            device_name TEXT,
            device_type TEXT,
            alarm_location TEXT,
            processing_state TEXT,
            guard_name TEXT,
            create_time INTEGER
        );

        CREATE TABLE IF NOT EXISTS fire_personnel (
            id TEXT PRIMARY KEY,
            name TEXT,
            station TEXT,
            role TEXT,
            phone TEXT
        );

        CREATE TABLE IF NOT EXISTS fire_equipment (
            id TEXT PRIMARY KEY,
            equipment_name TEXT,
            category TEXT,
            station TEXT,
            quantity INTEGER,
            status TEXT
        );

        CREATE TABLE IF NOT EXISTS fire_inspection (
            id TEXT PRIMARY KEY,
            unit_name TEXT,
            inspection_date TEXT,
            result TEXT,
            score INTEGER,
            issues_count INTEGER
        );
        """
    )

    # alarms
    cur.execute("SELECT COUNT(*) FROM fire_alarm_record")
    if cur.fetchone()[0] == 0:
        rng = random.Random(42)
        for i in range(240):
            create_time = now_ms - rng.randint(0, 180) * 24 * 3600 * 1000 - rng.randint(0, 24 * 3600 * 1000)
            cur.execute(
                """
                INSERT INTO fire_alarm_record (
                    id, unit_name, device_name, device_type, alarm_location,
                    processing_state, guard_name, create_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"ALARM{i:04d}",
                    rng.choice(units),
                    f"{rng.choice(['A', 'B', 'C'])}区{rng.choice(['1','2','3'])}层{rng.randint(1,30)}号",
                    rng.choice(device_types),
                    rng.choice(locations),
                    rng.choice(["未处理", "处理中", "已处理"]),
                    rng.choice(["陈**", "李**", "王**", "赵**", "周**"]),
                    create_time,
                ),
            )

    # personnel
    roles = ["值班员", "指挥员", "消防员", "通信员", "驾驶员"]
    cur.execute("SELECT COUNT(*) FROM fire_personnel")
    if cur.fetchone()[0] == 0:
        rng = random.Random(43)
        for i in range(80):
            cur.execute(
                """
                INSERT INTO fire_personnel (id, name, station, role, phone)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"P{i:04d}",
                    f"队员{i:02d}",
                    rng.choice(stations),
                    rng.choice(roles),
                    f"138{rng.randint(10000000, 99999999)}",
                ),
            )

    # equipment
    cur.execute("SELECT COUNT(*) FROM fire_equipment")
    if cur.fetchone()[0] == 0:
        rng = random.Random(44)
        for i in range(120):
            cur.execute(
                """
                INSERT INTO fire_equipment (id, equipment_name, category, station, quantity, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"E{i:04d}",
                    f"{rng.choice(equipment_categories)}-{rng.randint(1, 200)}",
                    rng.choice(equipment_categories),
                    rng.choice(stations),
                    rng.randint(1, 200),
                    rng.choice(["在库", "出库", "维修"]),
                ),
            )

    # inspection
    results = ["合格", "基本合格", "不合格"]
    cur.execute("SELECT COUNT(*) FROM fire_inspection")
    if cur.fetchone()[0] == 0:
        rng = random.Random(45)
        now_s = time.time()
        for i in range(120):
            day_offset = rng.randint(0, 180)
            date_str = time.strftime("%Y-%m-%d", time.localtime(now_s - day_offset * 86400))
            score = rng.randint(50, 100)
            res = "合格" if score >= 85 else ("基本合格" if score >= 70 else "不合格")
            cur.execute(
                """
                INSERT INTO fire_inspection (id, unit_name, inspection_date, result, score, issues_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"I{i:04d}",
                    rng.choice(units),
                    date_str,
                    res if rng.random() < 0.8 else rng.choice(results),
                    score,
                    rng.randint(0, 12),
                ),
            )

    conn.commit()
    conn.close()

