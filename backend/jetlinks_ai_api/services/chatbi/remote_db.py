from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import MetaData, Table, create_engine, inspect, select
from sqlalchemy.engine import Engine


class RemoteDBError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteTable:
    table: Table
    columns: list[tuple[str, str]]


def create_engine_from_url(db_url: str) -> Engine:
    if not db_url:
        raise RemoteDBError("数据库连接地址为空")
    return create_engine(db_url, pool_pre_ping=True, future=True)


def validate_tables(engine: Engine, tables: Iterable[str]) -> list[str]:
    inspector = inspect(engine)
    missing: list[str] = []
    for table in tables:
        if not inspector.has_table(table):
            missing.append(table)
    return missing


def load_table(engine: Engine, table_name: str) -> RemoteTable:
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    columns = [(col.name, str(col.type)) for col in table.columns]
    if not columns:
        raise RemoteDBError(f"无法读取表字段：{table_name}")
    return RemoteTable(table=table, columns=columns)


def iter_table_rows(engine: Engine, table: Table, batch_size: int, max_rows: int | None = None):
    fetched = 0
    with engine.connect() as conn:
        result = conn.execute(select(table))
        while True:
            if max_rows is not None:
                remaining = max_rows - fetched
                if remaining <= 0:
                    break
                batch = result.fetchmany(min(batch_size, remaining))
            else:
                batch = result.fetchmany(batch_size)
            if not batch:
                break
            fetched += len(batch)
            yield batch

