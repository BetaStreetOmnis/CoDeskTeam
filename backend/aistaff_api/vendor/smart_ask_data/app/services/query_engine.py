from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional, Sequence

from app.core.settings import Settings
from app.services.datasource_store import datasource_store
from app.services.llm.mock import MockLLM
from app.services.llm.openai_compatible import OpenAICompatibleLLM
from app.services.remote_db import RemoteDBError, create_engine_from_url, iter_table_rows, load_table


_DANGEROUS = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "TRUNCATE",
    "ALTER",
    "CREATE",
    "REPLACE",
    "ATTACH",
    "DETACH",
    "PRAGMA",
]


def _extract_sql(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    m = re.search(r"```sql\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip(";")

    m = re.search(r"\b(select|with)\b", raw, re.IGNORECASE)
    if m:
        return raw[m.start() :].strip().rstrip(";")

    return raw.strip().rstrip(";")


def _is_safe_select(sql: str) -> bool:
    sql_upper = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL).upper()
    sql_upper = re.sub(r"--.*?$", "", sql_upper, flags=re.MULTILINE).strip()
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        return False
    for keyword in _DANGEROUS:
        if re.search(rf"\b{re.escape(keyword)}\b", sql_upper):
            return False
    return True


def _tables_in_sql(sql: str) -> set[str]:
    sql_upper = sql.upper()

    cte_names: set[str] = set()
    m = re.match(r"\s*WITH\s+(?:RECURSIVE\s+)?", sql_upper)
    if m:
        i = m.end()
        while i < len(sql_upper):
            while i < len(sql_upper) and sql_upper[i] in " \t\r\n,":
                i += 1
            start = i
            while i < len(sql_upper) and (sql_upper[i].isalnum() or sql_upper[i] == "_"):
                i += 1
            name = sql_upper[start:i].strip()
            if not name:
                break
            while i < len(sql_upper) and sql_upper[i].isspace():
                i += 1
            if not sql_upper.startswith("AS", i):
                break
            i += 2
            while i < len(sql_upper) and sql_upper[i].isspace():
                i += 1
            if i >= len(sql_upper) or sql_upper[i] != "(":
                break
            cte_names.add(name.lower())
            depth = 0
            while i < len(sql_upper):
                if sql_upper[i] == "(":
                    depth += 1
                elif sql_upper[i] == ")":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            while i < len(sql_upper) and sql_upper[i].isspace():
                i += 1
            if i < len(sql_upper) and sql_upper[i] == ",":
                i += 1
                continue
            break

    tables = set()
    for keyword in ("FROM", "JOIN"):
        for m in re.finditer(rf"\b{keyword}\b\s+([^\s,;]+)", sql_upper):
            token = m.group(1).strip()
            if not token or token.startswith("("):
                continue
            token = token.strip('"`[]')
            token = token.strip("()")
            token = token.split(".")[-1]
            token = token.split()[0]
            if token:
                tables.add(token.lower())

    if cte_names:
        tables = {t for t in tables if t not in cte_names}
    return tables


def _quote_ident(name: str) -> str:
    return name.replace('"', '""')


def _chart_suggestion(question: str, data: list[dict]) -> dict | None:
    if not data:
        return None
    cols = list(data[0].keys())
    if len(cols) < 2:
        return {"type": "table", "title": question}

    def is_number(v: Any) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    numeric_cols = [c for c in cols if any(is_number(r.get(c)) for r in data)]
    text_cols = [c for c in cols if c not in numeric_cols]

    title = question if len(question) <= 24 else question[:24] + "…"

    def bar_multi(chart_type: str) -> dict | None:
        if len(text_cols) >= 2 and numeric_cols:
            return {
                "type": chart_type,
                "title": title,
                "xField": text_cols[0],
                "seriesField": text_cols[1],
                "valueField": numeric_cols[0],
            }
        if len(text_cols) >= 1 and len(numeric_cols) >= 2:
            return {"type": chart_type, "title": title, "xField": text_cols[0], "yFields": numeric_cols[:3]}
        return None

    if any(k in question for k in ["散点", "相关", "关联"]):
        if len(numeric_cols) >= 2:
            return {
                "type": "scatter",
                "title": title,
                "xField": numeric_cols[0],
                "yField": numeric_cols[1],
            }

    if any(k in question for k in ["堆叠", "叠加"]):
        cfg = bar_multi("bar_stack")
        if cfg:
            return cfg

    if any(k in question for k in ["对比", "分组", "对照"]):
        cfg = bar_multi("bar_group")
        if cfg:
            return cfg

    if any(k in question for k in ["条形", "横向", "横版"]):
        x = text_cols[0] if text_cols else cols[0]
        y = numeric_cols[0] if numeric_cols else cols[1]
        return {"type": "bar_horizontal", "title": title, "xField": x, "yField": y}

    if any(k in question for k in ["面积", "面积图"]):
        x = text_cols[0] if text_cols else cols[0]
        if len(numeric_cols) >= 2:
            return {"type": "area", "title": title, "xField": x, "yFields": numeric_cols[:3]}
        y = numeric_cols[0] if numeric_cols else cols[1]
        return {"type": "area", "title": title, "xField": x, "yField": y}

    if any(k in question for k in ["趋势", "走势", "变化", "按月", "按天"]):
        x = text_cols[0] if text_cols else cols[0]
        if len(numeric_cols) >= 2:
            return {"type": "line", "title": title, "xField": x, "yFields": numeric_cols[:3]}
        y = numeric_cols[0] if numeric_cols else cols[1]
        return {"type": "line", "title": title, "xField": x, "yField": y}

    if any(k in question for k in ["占比", "比例", "构成"]) and len(data) <= 12:
        name = cols[0]
        value = numeric_cols[0] if numeric_cols else cols[1]
        return {"type": "pie", "title": title, "nameField": name, "valueField": value}

    if any(k in question for k in ["热力", "热度", "矩阵"]) and len(cols) >= 3:
        x = cols[0]
        y = cols[1]
        v = numeric_cols[0] if numeric_cols else cols[2]
        return {"type": "heatmap", "title": title, "xField": x, "yField": y, "valueField": v}

    # 默认柱状图（类别-数值）
    x = text_cols[0] if text_cols else cols[0]
    y = numeric_cols[0] if numeric_cols else cols[1]
    return {"type": "bar", "title": title, "xField": x, "yField": y}


_CHART_LABELS = {
    "table": "表格",
    "line": "折线图",
    "area": "面积图",
    "bar": "柱状图",
    "bar_group": "分组柱状图",
    "bar_stack": "堆叠柱状图",
    "bar_horizontal": "横向条形图",
    "pie": "饼图",
    "scatter": "散点图",
    "heatmap": "热力图",
}


def _intent_desc(question: str, sql: str) -> str:
    q = question or ""
    if any(k in q for k in ["占比", "比例", "构成"]):
        return "占比/构成分析"
    if any(k in q for k in ["趋势", "走势", "按月", "按天", "变化"]):
        return "趋势分析"
    if any(k in q for k in ["排名", "TOP", "排行"]):
        return "排名统计"
    if "GROUP BY" in (sql or "").upper() or any(k in q for k in ["统计", "汇总", "分布"]):
        return "汇总统计"
    return "明细查询"


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _extract_clause(sql: str, start_kw: str, end_kws: Sequence[str]) -> str:
    if not sql:
        return ""
    m = re.search(rf"\b{start_kw}\b", sql, re.IGNORECASE)
    if not m:
        return ""
    tail = sql[m.end() :]
    end = len(tail)
    for kw in end_kws:
        m2 = re.search(rf"\b{kw}\b", tail, re.IGNORECASE)
        if m2:
            end = min(end, m2.start())
    return tail[:end].strip()


def _split_csv(text: str) -> list[str]:
    items: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch == "," and depth == 0:
            item = "".join(buf).strip()
            if item:
                items.append(item)
            buf = []
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        items.append(tail)
    return items


def _summarize_clause(text: str, max_len: int = 120) -> str:
    clean = _collapse_ws(text)
    if not clean:
        return ""
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1] + "…"


def _parse_limit(sql: str) -> int | None:
    if not sql:
        return None
    m = re.search(r"\bLIMIT\s+(\d+)\b", sql, re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _agg_functions(sql_upper: str) -> list[str]:
    funcs = []
    for name in ["COUNT", "SUM", "AVG", "MIN", "MAX"]:
        if f"{name}(" in sql_upper:
            funcs.append(name)
    return funcs


def _analysis_preview(cols: list[str], data: list[dict], limit: int = 3) -> str:
    samples: list[str] = []
    for row in data[:limit]:
        samples.append("、".join(f"{k}:{row.get(k)}" for k in cols[:4]))
    return "；".join(samples)


def _analyze(
    question: str,
    sql: str,
    data: list[dict],
    *,
    truncated: bool,
    max_rows: int,
    timeout_ms: int,
    used_tables: set[str] | None = None,
    datasource_names: list[str] | None = None,
    chart: dict | None = None,
    has_remote: bool = False,
) -> str:
    count = len(data)
    cols = list(data[0].keys()) if data else []
    intent = _intent_desc(question, sql)
    tables = sorted(used_tables or [])
    table_text = "、".join(tables) if tables else "系统自动选择"
    ds_text = "、".join(datasource_names or []) if datasource_names else "默认数据源"
    sql_upper = (sql or "").upper()
    chart_type = (chart or {}).get("type") if chart else None
    chart_label = _CHART_LABELS.get(chart_type or "table", str(chart_type or "表格"))
    field_text = "、".join(cols[:6]) if cols else ""
    where_raw = _extract_clause(sql, "WHERE", ["GROUP BY", "ORDER BY", "LIMIT", "HAVING", "UNION"])
    group_raw = _extract_clause(sql, "GROUP BY", ["ORDER BY", "LIMIT", "HAVING", "UNION"])
    order_raw = _extract_clause(sql, "ORDER BY", ["LIMIT", "UNION"])
    where_text = _summarize_clause(where_raw)
    group_fields = _split_csv(group_raw)
    order_fields = _split_csv(order_raw)
    group_text = "、".join(group_fields) if group_fields else ""
    order_text = "、".join(order_fields) if order_fields else ""
    limit_value = _parse_limit(sql)
    limit_text = str(limit_value) if limit_value is not None else "未设置"
    agg_funcs = _agg_functions(sql_upper)
    agg_text = "、".join(agg_funcs) if agg_funcs else "无"
    distinct = bool(re.search(r"\bSELECT\s+DISTINCT\b", sql or "", re.IGNORECASE))
    join_count = len(re.findall(r"\bJOIN\b", sql_upper))
    window_used = " OVER " in sql_upper
    dim_text = "、".join(group_fields) if group_fields else "无"
    timeout_text = f"{timeout_ms}ms" if timeout_ms > 0 else "未限制"
    multi_source = len(datasource_names or []) > 1

    analysis = [
        "思考过程：",
        f"1) 意图识别：{intent}，明确查询目标与结果形态。",
        f"2) 数据源选择：{ds_text}；涉及表：{table_text}。",
        f"3) 维度与指标：维度={dim_text}；聚合函数={agg_text}；去重={'是' if distinct else '否'}"
        f"{'；包含窗口函数' if window_used else ''}。",
        f"4) 查询约束：过滤={where_text or '无'}；分组={group_text or '无'}；"
        f"排序={order_text or '无'}；LIMIT={limit_text}（返回上限 {max_rows}）。",
        f"5) 执行与安全：仅SELECT；表权限校验；超时控制≤{timeout_text}；跨源联表={'是' if multi_source else '否'}"
        f"（JOIN {join_count} 次，远程表={'是' if has_remote else '否'}）。",
    ]

    if count:
        truncated_text = f"，结果已截断，仅展示前 {max_rows} 条" if truncated else ""
        analysis.append(f"6) 执行结果：返回 {count} 条记录{truncated_text}。")
        if field_text:
            suffix = "…" if len(cols) > 6 else ""
            analysis.append(f"7) 字段输出：{field_text}{suffix}。")
        analysis.append(f"8) 展现策略：以{chart_label}为主，保留表格供导出与上屏。")
    else:
        analysis.append("6) 执行结果：未查询到符合条件的数据。")
        analysis.append("7) 展现策略：提示空结果，可调整时间范围或筛选条件后重试。")

    analysis.append("")
    analysis.append("结果摘要：")
    analysis.append(f"- 记录数：{count} 条")
    if truncated:
        analysis.append(f"- 展示：仅展示前 {max_rows} 条")
    if cols:
        analysis.append(f"- 字段：{field_text}{'…' if len(cols) > 6 else ''}")
    if count:
        preview = _analysis_preview(cols, data, limit=3)
        if preview:
            analysis.append(f"- 示例：{preview}")

    return "\n".join(analysis)


@dataclass(frozen=True)
class _Datasource:
    id: str
    name: str
    tables: list[str]
    db_path: str
    db_type: str
    db_url: str


@dataclass(frozen=True)
class _TableRef:
    alias: str
    table: str
    db_path: str
    db_type: str
    db_url: str
    datasource_id: str


class QueryEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db_path = settings.demo_db_path
        sources = datasource_store.list_sources(settings.demo_db_path)
        self._datasources = [
            _Datasource(
                id=src.id,
                name=src.name,
                tables=list(src.tables),
                db_path=src.db_path,
                db_type=src.db_type,
                db_url=src.db_url,
            )
            for src in sources
        ]
        self._datasource_map = {src.id: src for src in self._datasources}
        self._table_map: dict[str, _TableRef] = {}
        for src in self._datasources:
            for table in src.tables:
                alias = self._table_alias(src, table)
                key = alias.lower()
                self._table_map[key] = _TableRef(
                    alias=alias,
                    table=table,
                    db_path=src.db_path,
                    db_type=src.db_type,
                    db_url=src.db_url,
                    datasource_id=src.id,
                )

        if settings.llm_provider == "openai_compatible":
            self._llm = OpenAICompatibleLLM(
                base_url=settings.openai_base_url,
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                wire_api=getattr(settings, "openai_wire_api", "chat_completions"),
            )
        else:
            self._llm = MockLLM()

    def _table_alias(self, datasource: _Datasource, table: str) -> str:
        if datasource.db_type == "sqlite" and datasource.db_path == self._db_path:
            return table
        return f"{datasource.id}__{table}"

    def _allowed_tables(self, datasource_ids: Sequence[str]) -> set[str]:
        allow = set()
        for sid in datasource_ids:
            src = self._datasource_map.get(sid)
            if src:
                for t in src.tables:
                    allow.add(self._table_alias(src, t).lower())
        return allow

    def _schema_text(self, allowed_tables: set[str]) -> str:
        refs = [self._table_map[t] for t in sorted(allowed_tables) if t in self._table_map]
        if not refs:
            return ""
        lines: list[str] = []

        sqlite_refs = [ref for ref in refs if ref.db_type == "sqlite"]
        remote_refs = [ref for ref in refs if ref.db_type != "sqlite"]

        grouped: dict[str, list[_TableRef]] = defaultdict(list)
        for ref in sqlite_refs:
            grouped[ref.db_path].append(ref)

        for db_path, items in grouped.items():
            try:
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                for ref in items:
                    try:
                        cur.execute(f'PRAGMA table_info("{_quote_ident(ref.table)}")')
                        cols = [f"{r[1]}({r[2]})" for r in cur.fetchall()]
                        suffix = f" [来源:{ref.datasource_id}]" if ref.alias != ref.table else ""
                        lines.append(f"- {ref.alias}: " + ", ".join(cols) + suffix)
                    except Exception:
                        lines.append(f"- {ref.alias}: (无法读取字段)")
            except Exception:
                for ref in items:
                    lines.append(f"- {ref.alias}: (无法连接数据库)")
            finally:
                try:
                    conn.close()  # type: ignore[maybe-undefined]
                except Exception:
                    pass

        remote_grouped: dict[str, list[_TableRef]] = defaultdict(list)
        for ref in remote_refs:
            remote_grouped[ref.db_url].append(ref)

        for db_url, items in remote_grouped.items():
            engine = None
            try:
                engine = create_engine_from_url(db_url)
                for ref in items:
                    try:
                        remote_table = load_table(engine, ref.table)
                        cols = [f"{name}({typ})" for name, typ in remote_table.columns]
                        suffix = f" [来源:{ref.datasource_id}]" if ref.alias != ref.table else ""
                        lines.append(f"- {ref.alias}: " + ", ".join(cols) + suffix)
                    except Exception:
                        lines.append(f"- {ref.alias}: (无法读取字段)")
            except Exception:
                for ref in items:
                    lines.append(f"- {ref.alias}: (无法连接数据库)")
            finally:
                if engine is not None:
                    engine.dispose()

        return "\n".join(lines)

    def _prompt(self, question: str, allowed_tables: set[str], history: list[dict]) -> str:
        schema = self._schema_text(allowed_tables)
        history_text = ""
        if history:
            tail = history[-6:]
            history_text = "\n".join(f"{m.get('role','')}: {m.get('content','')}" for m in tail)

        allowed_names = [
            (self._table_map[t].alias if t in self._table_map else t) for t in sorted(allowed_tables)
        ]

        return (
            "请根据用户问题生成SQLite的SELECT查询SQL，只返回SQL。\n"
            "规则：\n"
            "1) 只能SELECT，禁止写入/DDL\n"
            "2) 时间戳字段create_time为毫秒，转换: datetime(create_time/1000,'unixepoch','localtime')\n"
            "3) 尽量给字段起中文别名\n"
            f"4) 仅允许访问这些表：{', '.join(allowed_names)}\n"
            f"5) 必须带 LIMIT，且不超过 {self._settings.sql_max_rows}\n\n"
            f"表结构：\n{schema}\n\n"
            + (f"对话历史：\n{history_text}\n\n" if history_text else "")
            + f"问题：{question}\n\nSQL："
        )

    async def classify_intent(self, question: str, history: list[dict]) -> str:
        try:
            intent = await self._llm.classify_intent(question, history)
        except Exception:
            return "unknown"
        intent = (intent or "").strip().lower()
        if intent in {"chat", "data"}:
            return intent
        return "unknown"

    async def chat(self, question: str, history: list[dict]) -> str:
        try:
            reply = await self._llm.chat(question, history)
        except Exception:
            return ""
        return (reply or "").strip()

    async def explain_sql(self, question: str, sql: str) -> str:
        if not question or not sql:
            return ""
        try:
            reply = await self._llm.explain_sql(question, sql)
        except Exception:
            return ""
        return (reply or "").strip()

    async def ask(self, question: str, datasource_ids: Sequence[str], history: list[dict]) -> dict:
        allowed = self._allowed_tables(datasource_ids)
        if not allowed:
            return {"success": False, "error": "未选择可用数据源"}

        prompt = self._prompt(question, allowed, history)
        try:
            raw = await self._llm.generate_sql(prompt)
        except Exception as e:
            raw = ""
        sql = _extract_sql(raw)
        if not sql:
            sql = _extract_sql(prompt)  # 不太可能命中，兜底

        if not _is_safe_select(sql):
            # 回退到mock规则，保证可演示
            sql = await MockLLM().generate_sql(f"问题：{question}")

        result = await self.run_sql(sql=sql, datasource_ids=datasource_ids, question=question)
        if result.get("success"):
            sql_explain = await self.explain_sql(question, result.get("sql") or "")
            if sql_explain:
                result["sql_explain"] = sql_explain
        return result

    async def ask_stream(
        self, question: str, datasource_ids: Sequence[str], history: list[dict]
    ) -> AsyncIterator[dict]:
        allowed = self._allowed_tables(datasource_ids)
        if not allowed:
            yield {"type": "error", "error": "未选择可用数据源"}
            return

        char_delay = max(0, int(self._settings.stream_char_delay_ms)) / 1000.0
        stage_delay = max(0, int(self._settings.stream_stage_delay_ms)) / 1000.0

        prompt = self._prompt(question, allowed, history)
        try:
            raw = await self._llm.generate_sql(prompt)
        except Exception:
            raw = ""
        sql = _extract_sql(raw)
        if not sql:
            sql = _extract_sql(prompt)  # 不太可能命中，兜底

        if not _is_safe_select(sql):
            sql = await MockLLM().generate_sql(f"问题：{question}")

        result_task = asyncio.create_task(
            self.run_sql(sql=sql, datasource_ids=datasource_ids, question=question)
        )

        sql_explain = ""
        try:
            sql_explain = await self.explain_sql(question, sql)
        except Exception:
            sql_explain = ""

        if not sql_explain:
            sql_explain = "（说明生成失败，已直接展示SQL）"
        for ch in sql_explain:
            yield {"type": "sql_explain_delta", "delta": ch}
            if char_delay:
                await asyncio.sleep(char_delay)
        yield {"type": "sql_explain", "sql_explain": sql_explain}

        if stage_delay:
            await asyncio.sleep(stage_delay)

        if sql:
            for ch in sql:
                yield {"type": "sql_delta", "delta": ch}
                if char_delay:
                    await asyncio.sleep(char_delay)
            yield {"type": "sql", "sql": sql}

        try:
            result = await result_task
        except Exception as e:
            msg = str(e).strip() or "查询失败"
            yield {"type": "error", "error": msg}
            return

        if result.get("success"):
            if sql_explain and not result.get("sql_explain"):
                result["sql_explain"] = sql_explain
            analysis_text = (result.get("analysis") or "").strip()
            if analysis_text:
                for ch in analysis_text:
                    yield {"type": "analysis_delta", "delta": ch}
                    if char_delay:
                        await asyncio.sleep(char_delay)
                yield {"type": "analysis", "analysis": analysis_text}
            yield {"type": "result", "result": result}
        else:
            yield {"type": "error", "error": result.get("error", "查询失败")}

    async def run_sql(self, sql: str, datasource_ids: Sequence[str], question: Optional[str] = None) -> dict:
        allowed = self._allowed_tables(datasource_ids)
        if not allowed:
            return {"success": False, "error": "未选择可用数据源"}

        sql = _extract_sql(sql)
        if not sql:
            return {"success": False, "error": "SQL为空"}
        if not _is_safe_select(sql):
            return {"success": False, "error": "仅允许执行安全的SELECT查询"}

        used_tables = _tables_in_sql(sql)
        if used_tables and not used_tables.issubset(allowed):
            return {
                "success": False,
                "error": f"SQL引用了未授权表：{', '.join(sorted(used_tables - allowed))}",
            }

        try:
            data, truncated = await asyncio.to_thread(
                self._execute, sql, datasource_ids, used_tables if used_tables else None
            )
        except Exception as e:
            msg = str(e).strip() or "SQL执行失败"
            return {"success": False, "error": msg}

        chart = _chart_suggestion(question or "查询结果", data)
        used_refs = [self._table_map[t] for t in sorted(used_tables) if t in self._table_map]
        table_labels = {ref.alias for ref in used_refs} if used_refs else set(used_tables)
        ds_names = {
            self._datasource_map[ref.datasource_id].name
            for ref in used_refs
            if ref.datasource_id in self._datasource_map
        }
        if not ds_names:
            ds_names = {
                self._datasource_map[sid].name
                for sid in datasource_ids
                if sid in self._datasource_map
            }
        analysis = _analyze(
            question or "查询",
            sql,
            data,
            truncated=truncated,
            max_rows=self._settings.sql_max_rows,
            timeout_ms=self._settings.sql_timeout_ms,
            used_tables=table_labels,
            datasource_names=sorted(ds_names),
            chart=chart,
            has_remote=any(ref.db_type != "sqlite" for ref in used_refs),
        )
        return {
            "success": True,
            "question": question,
            "sql": sql,
            "data": data,
            "count": len(data),
            "truncated": truncated,
            "max_rows": self._settings.sql_max_rows,
            "analysis": analysis,
            "chart": chart,
        }

    def _execute(
        self, sql: str, datasource_ids: Sequence[str], used_tables: set[str] | None = None
    ) -> tuple[list[dict], bool]:
        max_rows = max(1, int(self._settings.sql_max_rows))
        timeout_ms = max(0, int(self._settings.sql_timeout_ms))

        start = time.monotonic()
        conn = sqlite3.connect(self._db_path)
        try:
            conn.row_factory = sqlite3.Row
            if timeout_ms > 0:

                def _progress_handler() -> int:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    return 1 if elapsed_ms > timeout_ms else 0

                conn.set_progress_handler(_progress_handler, 10_000)

            self._prepare_connection(conn, datasource_ids, used_tables)
            cur = conn.cursor()
            cur.execute(sql)

            rows = cur.fetchmany(max_rows + 1)
            truncated = len(rows) > max_rows
            if truncated:
                rows = rows[:max_rows]

            result: list[dict] = []
            for r in rows:
                result.append({k: r[k] for k in r.keys()})
            return result, truncated
        except sqlite3.OperationalError as e:
            if "interrupted" in str(e).lower():
                raise RuntimeError(f"SQL执行超时（>{timeout_ms}ms）") from e
            raise RuntimeError(f"SQL执行失败：{e}") from e
        finally:
            conn.close()

    def _map_remote_type(self, raw: str) -> str:
        t = (raw or "").lower()
        if any(k in t for k in ["int", "serial", "bigint", "smallint", "tinyint", "bool", "boolean"]):
            return "INTEGER"
        if any(k in t for k in ["decimal", "numeric", "real", "double", "float"]):
            return "REAL"
        if any(k in t for k in ["blob", "binary", "bytea"]):
            return "BLOB"
        return "TEXT"

    def _normalize_remote_value(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, bytearray):
            return bytes(value)
        return value

    def _load_remote_table(
        self, conn: sqlite3.Connection, src: _Datasource, table: str, alias_table: str
    ) -> None:
        engine = None
        try:
            engine = create_engine_from_url(src.db_url)
            remote_table = load_table(engine, table)
            col_defs = []
            col_names = []
            for name, typ in remote_table.columns:
                col_names.append(name)
                col_defs.append(f'"{_quote_ident(name)}" {self._map_remote_type(typ)}')
            if not col_names:
                raise RemoteDBError(f"表结构为空：{table}")

            conn.execute(
                f'CREATE TEMP TABLE IF NOT EXISTS "{_quote_ident(alias_table)}" '
                f'({", ".join(col_defs)})'
            )

            cols_sql = ", ".join(f'"{_quote_ident(c)}"' for c in col_names)
            placeholders = ", ".join("?" for _ in col_names)
            insert_sql = (
                f'INSERT INTO "{_quote_ident(alias_table)}" ({cols_sql}) VALUES ({placeholders})'
            )

            max_rows = int(self._settings.federated_max_rows_per_table)
            batch_size = int(self._settings.federated_batch_size)
            for batch in iter_table_rows(engine, remote_table.table, batch_size, max_rows=max_rows):
                values = [
                    tuple(self._normalize_remote_value(v) for v in row)
                    for row in batch
                ]
                conn.executemany(insert_sql, values)
            conn.commit()
        except RemoteDBError as e:
            raise RuntimeError(str(e)) from e
        except Exception as e:
            raise RuntimeError(f"远程表加载失败：{e}") from e
        finally:
            if engine is not None:
                engine.dispose()

    def _prepare_connection(
        self,
        conn: sqlite3.Connection,
        datasource_ids: Sequence[str],
        used_tables: set[str] | None = None,
    ) -> None:
        ids = set(datasource_ids)
        want = {t.lower() for t in used_tables} if used_tables else None
        attached: set[str] = set()
        for src in self._datasources:
            if src.id not in ids:
                continue
            if src.db_type == "sqlite":
                if src.db_path == self._db_path:
                    continue
                alias = f"ds_{src.id}"
                if alias not in attached:
                    conn.execute(f"ATTACH DATABASE ? AS {alias}", (src.db_path,))
                    attached.add(alias)
                for table in src.tables:
                    alias_table = self._table_alias(src, table)
                    if want and alias_table.lower() not in want and table.lower() not in want:
                        continue
                    conn.execute(
                        f'CREATE TEMP VIEW IF NOT EXISTS "{_quote_ident(alias_table)}" '
                        f'AS SELECT * FROM "{_quote_ident(alias)}"."{_quote_ident(table)}"'
                    )
            else:
                for table in src.tables:
                    alias_table = self._table_alias(src, table)
                    if want and alias_table.lower() not in want and table.lower() not in want:
                        continue
                    self._load_remote_table(conn, src, table, alias_table)
