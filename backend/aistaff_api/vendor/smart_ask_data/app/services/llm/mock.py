from __future__ import annotations

import re
from typing import Iterable

from app.services.llm.base import LLMClient


_SMALLTALK = {
    "你好",
    "您好",
    "嗨",
    "哈喽",
    "hello",
    "hi",
    "hey",
    "早上好",
    "下午好",
    "晚上好",
    "在吗",
    "在么",
    "再见",
    "拜拜",
    "bye",
    "谢谢",
    "多谢",
}


def _normalize_text(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", (text or "").lower())


def _looks_like_smalltalk(question: str) -> bool:
    text = _normalize_text(question)
    if not text:
        return True
    if text in _SMALLTALK:
        return True
    if text.startswith("你好") and len(text) <= 4:
        return True
    return False


class MockLLM(LLMClient):
    async def chat(self, question: str, history: list[dict]) -> str:
        return ""

    async def explain_sql(self, question: str, sql: str) -> str:
        return ""

    async def classify_intent(self, question: str, history: list[dict]) -> str:
        return "chat" if _looks_like_smalltalk(question) else "data"

    async def generate_sql(self, prompt: str) -> str:
        question = _extract_last_question(prompt)
        history_questions = _extract_history_user_questions(prompt)
        return _rule_based_sql(question, history_questions)


def _extract_last_question(prompt: str) -> str:
    matches = re.findall(r"问题\s*[:：]\s*(.*)", prompt)
    if matches:
        return (matches[-1] or "").strip()
    return (prompt or "").strip()


def _extract_history_user_questions(prompt: str) -> list[str]:
    questions: list[str] = []
    for line in (prompt or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.lower().startswith("user:"):
            questions.append(s.split(":", 1)[1].strip())
        elif s.startswith("用户:") or s.startswith("用户："):
            questions.append(s.split(":", 1)[1].strip() if ":" in s else s.split("：", 1)[1].strip())
    return [q for q in questions if q]


def _first_non_none(*values):
    for v in values:
        if v is not None:
            return v
    return None


def _parse_top_n(text: str, default: int = 20) -> int:
    m = re.search(r"top\s*(\d+)", text, re.IGNORECASE)
    if m:
        try:
            return max(1, int(m.group(1)))
        except ValueError:
            pass
    m = re.search(r"前\s*(\d+)\s*名", text)
    if m:
        try:
            return max(1, int(m.group(1)))
        except ValueError:
            pass
    return default


def _parse_days(text: str) -> int | None:
    if any(k in text for k in ["最近7天", "近7天", "7天", "近一周", "最近一周"]):
        return 7
    if any(k in text for k in ["最近30天", "近30天", "30天", "近一月", "最近一月", "近一个月", "最近一个月"]):
        return 30
    if any(k in text for k in ["近90天", "90天", "近三月", "最近三月", "近3月", "最近3月"]):
        return 90
    if any(k in text for k in ["近半年", "最近半年"]):
        return 180
    return None


def _detect_topics(text: str) -> set[str]:
    topics: set[str] = set()
    if any(k in text for k in ["火警", "警情", "报警", "接警"]):
        topics.add("alarm")
    if any(k in text for k in ["人员", "消防员", "队员", "值班员", "指挥员", "岗位"]):
        topics.add("personnel")
    if any(k in text for k in ["装备", "物资", "库存", "器材"]):
        topics.add("equipment")
    if any(k in text for k in ["检查", "监督", "得分", "隐患", "问题数", "问题"]):
        topics.add("inspection")
    return topics


def _detect_processing_state(text: str) -> str | None:
    if any(k in text for k in ["未处理", "待处理"]):
        return "未处理"
    if "处理中" in text:
        return "处理中"
    if "已处理" in text:
        return "已处理"
    return None


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(k in text for k in keywords)


def _rule_based_sql(question: str, history_questions: list[str]) -> str:
    q = question.strip()
    q_lower = q.lower()
    history_text = " ".join(history_questions[-3:]).strip()

    topics = _detect_topics(q)
    if not topics and history_text:
        topics = _detect_topics(history_text)
    if not topics:
        topics = {"alarm"}

    top_n = _parse_top_n(q, default=20)
    days = _first_non_none(_parse_days(q), _parse_days(history_text))
    state = _first_non_none(_detect_processing_state(q), _detect_processing_state(history_text) if "只看" in q or "仅看" in q else None)

    want_today = _contains_any(q, ["今天", "今日"]) or "today" in q_lower
    want_trend = _contains_any(q, ["趋势", "走势", "变化", "按月", "月份", "月度", "按天", "每日"])
    want_month = _contains_any(q, ["按月", "月份", "月度"]) or ("趋势" in q and "月" in q)
    want_day = _contains_any(q, ["按天", "每日"]) or ("趋势" in q and "天" in q)
    want_ratio = _contains_any(q, ["占比", "比例", "构成"])
    want_group_unit = _contains_any(q, ["按单位", "按联网单位", "单位排名"]) or ("单位" in q and _contains_any(q, ["统计", "排名", "top", "TOP"]))
    want_group_station = _contains_any(q, ["按站点", "站点排名"]) or ("站点" in q and _contains_any(q, ["统计", "排名", "top", "TOP"]))
    want_top = _contains_any(q, ["排名", "最多"]) or ("top" in q_lower)

    is_followup = _contains_any(q, ["再", "继续", "同样", "还是", "只看", "仅看", "在此基础上", "然后"])
    if is_followup and history_text:
        if not want_month and _contains_any(history_text, ["按月", "月份", "月度"]):
            want_month = True
        if not want_day and _contains_any(history_text, ["按天", "每日"]):
            want_day = True
        if not want_ratio and _contains_any(history_text, ["占比", "比例", "构成"]):
            want_ratio = True
        if not want_group_unit and _contains_any(history_text, ["按单位", "按联网单位", "单位排名"]):
            want_group_unit = True
        if not want_group_station and _contains_any(history_text, ["按站点", "站点排名"]):
            want_group_station = True
        if not want_top and _contains_any(history_text, ["排名", "top", "TOP", "最多"]):
            want_top = True

    # 1) 多源联动：站点人员 + 装备库存
    if topics.issuperset({"personnel", "equipment"}) and _contains_any(q, ["站点", "人员", "装备"]):
        return (
            "SELECT p.station AS 站点, "
            "COUNT(DISTINCT p.id) AS 人员数量, "
            "COALESCE(SUM(e.quantity), 0) AS 装备库存数量, "
            "COUNT(DISTINCT e.id) AS 装备条目数 "
            "FROM fire_personnel p "
            "LEFT JOIN fire_equipment e ON e.station = p.station "
            "GROUP BY p.station "
            "ORDER BY 装备库存数量 DESC "
            f"LIMIT {min(top_n, 50)}"
        )

    # 2) 多源联动：单位火警数量 + 监督检查得分
    if topics.issuperset({"alarm", "inspection"}) and _contains_any(q, ["单位", "火警", "检查", "得分"]):
        window = int(days or 30)
        return (
            "WITH a AS ("
            "  SELECT unit_name AS unit_name, COUNT(*) AS alarm_count "
            "  FROM fire_alarm_record "
            f"  WHERE create_time >= (strftime('%s','now','-{window} day') * 1000) "
            "  GROUP BY unit_name"
            "), i AS ("
            "  SELECT unit_name AS unit_name, ROUND(AVG(score), 1) AS avg_score, SUM(issues_count) AS issues_total "
            "  FROM fire_inspection "
            f"  WHERE inspection_date >= date('now','-{window} day') "
            "  GROUP BY unit_name"
            ") "
            f"SELECT a.unit_name AS 单位, a.alarm_count AS 火警数量, i.avg_score AS 近{window}天检查均分, i.issues_total AS 问题总数 "
            "FROM a LEFT JOIN i ON i.unit_name = a.unit_name "
            "ORDER BY 火警数量 DESC "
            f"LIMIT {min(top_n, 50)}"
        )

    # 3) 火警/警情
    if "alarm" in topics:
        where = []
        if want_today:
            where.append(
                "date(datetime(create_time/1000,'unixepoch','localtime')) = date('now','localtime')"
            )
        elif days:
            where.append(f"create_time >= (strftime('%s','now','-{int(days)} day') * 1000)")
        if state:
            where.append(f"processing_state = '{state}'")
        where_sql = ("WHERE " + " AND ".join(where) + " ") if where else ""

        if want_month:
            return (
                "SELECT strftime('%Y-%m', datetime(create_time/1000,'unixepoch','localtime')) AS 月份, "
                "COUNT(*) AS 火警数量 "
                "FROM fire_alarm_record "
                + where_sql
                + "GROUP BY 月份 ORDER BY 月份 "
                + "LIMIT 24"
            )
        if want_day:
            window = int(days or 30)
            return (
                "SELECT date(datetime(create_time/1000,'unixepoch','localtime')) AS 日期, "
                "COUNT(*) AS 火警数量 "
                "FROM fire_alarm_record "
                f"WHERE create_time >= (strftime('%s','now','-{window} day') * 1000) "
                + (f"AND processing_state = '{state}' " if state else "")
                + "GROUP BY 日期 ORDER BY 日期 "
                + f"LIMIT {min(window + 3, 60)}"
            )
        if want_ratio:
            window = int(days or 7)
            return (
                "SELECT processing_state AS 处理状态, COUNT(*) AS 数量 "
                "FROM fire_alarm_record "
                f"WHERE create_time >= (strftime('%s','now','-{window} day') * 1000) "
                "GROUP BY processing_state ORDER BY 数量 DESC "
                "LIMIT 12"
            )
        if want_group_unit or want_top:
            if _contains_any(q, ["位置", "地点", "报警位置"]):
                return (
                    "SELECT alarm_location AS 报警位置, COUNT(*) AS 报警次数 "
                    "FROM fire_alarm_record "
                    + where_sql
                    + "GROUP BY alarm_location ORDER BY 报警次数 DESC "
                    + f"LIMIT {min(top_n, 50)}"
                )
            return (
                "SELECT unit_name AS 联网单位, COUNT(*) AS 火警数量 "
                "FROM fire_alarm_record "
                + where_sql
                + "GROUP BY unit_name ORDER BY 火警数量 DESC "
                + f"LIMIT {min(top_n, 50)}"
            )
        # 明细列表
        return (
            "SELECT unit_name AS 联网单位, device_name AS 设备名称, alarm_location AS 报警位置, "
            "processing_state AS 处理状态, guard_name AS 值班人员, "
            "datetime(create_time/1000,'unixepoch','localtime') AS 报警时间 "
            "FROM fire_alarm_record "
            + where_sql
            + "ORDER BY create_time DESC "
            + "LIMIT 100"
        )

    # 4) 装备物资
    if "equipment" in topics:
        if want_group_station or want_top:
            return (
                "SELECT station AS 站点, SUM(quantity) AS 库存数量 "
                "FROM fire_equipment "
                "GROUP BY station ORDER BY 库存数量 DESC "
                f"LIMIT {min(top_n, 50)}"
            )
        return (
            "SELECT station AS 站点, category AS 装备类别, SUM(quantity) AS 库存数量 "
            "FROM fire_equipment "
            "GROUP BY station, category "
            "ORDER BY 库存数量 DESC "
            f"LIMIT {min(top_n, 80)}"
        )

    # 5) 人员
    if "personnel" in topics:
        if _contains_any(q, ["岗位", "角色"]):
            return (
                "SELECT role AS 岗位, COUNT(*) AS 人员数量 "
                "FROM fire_personnel "
                "GROUP BY role ORDER BY 人员数量 DESC "
                f"LIMIT {min(top_n, 50)}"
            )
        return (
            "SELECT station AS 站点, COUNT(*) AS 人员数量 "
            "FROM fire_personnel "
            "GROUP BY station ORDER BY 人员数量 DESC "
            f"LIMIT {min(top_n, 50)}"
        )

    # 6) 监督检查
    if "inspection" in topics:
        window = int(days or 30)
        if want_trend and want_month:
            return (
                "SELECT substr(inspection_date, 1, 7) AS 月份, ROUND(AVG(score), 1) AS 平均得分 "
                "FROM fire_inspection "
                f"WHERE inspection_date >= date('now','-{window} day') "
                "GROUP BY 月份 ORDER BY 月份 "
                "LIMIT 24"
            )
        return (
            "SELECT unit_name AS 单位, ROUND(AVG(score), 1) AS 平均得分, SUM(issues_count) AS 问题总数 "
            "FROM fire_inspection "
            f"WHERE inspection_date >= date('now','-{window} day') "
            "GROUP BY unit_name "
            "ORDER BY 平均得分 DESC "
            f"LIMIT {min(top_n, 80)}"
        )

    # 兜底
    return (
        "SELECT unit_name AS 联网单位, COUNT(*) AS 火警数量 "
        "FROM fire_alarm_record "
        "GROUP BY unit_name ORDER BY 火警数量 DESC LIMIT 20"
    )
