from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path
import os

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from jetlinks_ai_api.env_utils import env_str


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# We manage migrations with explicit revision scripts (no autogenerate for now).
target_metadata = None


def _normalize_sqlalchemy_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return raw

    lowered = raw.lower()
    if lowered.startswith("postgresql+psycopg://"):
        return raw
    if lowered.startswith("postgresql+asyncpg://"):
        return f"postgresql+psycopg://{raw.split('://', 1)[1]}"
    if lowered.startswith("postgresql://"):
        return f"postgresql+psycopg://{raw.split('://', 1)[1]}"
    if lowered.startswith("postgres://"):
        return f"postgresql+psycopg://{raw.split('://', 1)[1]}"
    return raw


def _default_sqlite_url() -> str:
    repo_root = Path(__file__).resolve().parents[2]

    preferred_dir = repo_root / ".jetlinks-ai"
    legacy_dir = repo_root / ".aistaff"
    data_dir = preferred_dir if preferred_dir.exists() else legacy_dir if legacy_dir.exists() else preferred_dir
    default_db_path = data_dir / "jetlinks_ai.db"
    if data_dir.name == ".aistaff" and (data_dir / "aistaff.db").exists() and not default_db_path.exists():
        default_db_path = data_dir / "aistaff.db"

    db_path = Path(env_str("DB_PATH", str(default_db_path)) or str(default_db_path)).expanduser().resolve()
    return f"sqlite:///{db_path}"


def get_url() -> str:
    db_url = (env_str("DB_URL", "") or "").strip()
    if db_url:
        return _normalize_sqlalchemy_url(db_url)
    return _default_sqlite_url()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(get_url(), poolclass=NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
