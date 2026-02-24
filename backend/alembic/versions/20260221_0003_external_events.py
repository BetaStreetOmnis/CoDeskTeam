"""external events (dedup)

Revision ID: 20260221_0003
Revises: 20260221_0002
Create Date: 2026-02-21
"""

from __future__ import annotations

from alembic import op


revision = "20260221_0003"
down_revision = "20260221_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    statements = [
        """
        CREATE TABLE IF NOT EXISTS external_events (
          id BIGSERIAL PRIMARY KEY,
          team_id BIGINT NOT NULL,
          provider TEXT NOT NULL,
          external_id TEXT NOT NULL,
          session_id TEXT NULL,
          user_id BIGINT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(team_id, provider, external_id),
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_external_events_team_id ON external_events(team_id)",
    ]

    for stmt in statements:
        op.execute(stmt)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("DROP TABLE IF EXISTS external_events")

