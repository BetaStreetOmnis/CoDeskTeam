from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = "智能问数"
    app_version: str = "0.1.0"
    debug: bool = True

    session_secret: str = os.getenv("SMARTASK_SESSION_SECRET", "dev-secret-change-me")
    session_https_only: bool = _env_bool("SMARTASK_SESSION_HTTPS_ONLY", False)
    session_same_site: str = os.getenv("SMARTASK_SESSION_SAMESITE", "lax")

    cors_allow_origins: list[str] = None  # type: ignore[assignment]

    llm_provider: str = os.getenv("SMARTASK_LLM_PROVIDER", "mock")
    openai_base_url: str = os.getenv("SMARTASK_OPENAI_BASE_URL", "")
    openai_api_key: str = os.getenv("SMARTASK_OPENAI_API_KEY", "")
    openai_model: str = os.getenv("SMARTASK_OPENAI_MODEL", "gpt-4o-mini")
    openai_wire_api: str = os.getenv("SMARTASK_OPENAI_WIRE_API", "chat_completions")

    sql_max_rows: int = _env_int("SMARTASK_SQL_MAX_ROWS", 800)
    sql_timeout_ms: int = _env_int("SMARTASK_SQL_TIMEOUT_MS", 6000)
    stream_char_delay_ms: int = _env_int("SMARTASK_STREAM_CHAR_DELAY_MS", 8)
    stream_stage_delay_ms: int = _env_int("SMARTASK_STREAM_STAGE_DELAY_MS", 250)
    federated_max_rows_per_table: int = _env_int("SMARTASK_FEDERATED_MAX_ROWS", 20000)
    federated_batch_size: int = _env_int("SMARTASK_FEDERATED_BATCH_SIZE", 2000)

    demo_db_path: str = os.getenv(
        "SMARTASK_DEMO_DB_PATH",
        str(Path(__file__).resolve().parents[2] / "storage" / "demo.db"),
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "cors_allow_origins", _env_list("SMARTASK_CORS_ORIGINS", ["*"]))
        object.__setattr__(self, "sql_max_rows", max(1, self.sql_max_rows))
        object.__setattr__(self, "sql_timeout_ms", max(0, self.sql_timeout_ms))
        object.__setattr__(self, "stream_char_delay_ms", max(0, self.stream_char_delay_ms))
        object.__setattr__(self, "stream_stage_delay_ms", max(0, self.stream_stage_delay_ms))
        object.__setattr__(self, "federated_max_rows_per_table", max(1, self.federated_max_rows_per_table))
        object.__setattr__(self, "federated_batch_size", max(1, self.federated_batch_size))


_SETTINGS: Settings | None = None


def get_settings() -> Settings:
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = Settings(debug=_env_bool("SMARTASK_DEBUG", True))
    return _SETTINGS
