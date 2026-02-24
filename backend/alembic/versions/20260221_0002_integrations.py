"""integration tokens + external identities (postgres)

Revision ID: 20260221_0002
Revises: 20260220_0001
Create Date: 2026-02-21
"""

from __future__ import annotations

from alembic import op


revision = "20260221_0002"
down_revision = "20260220_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    statements = [
        """
        CREATE TABLE IF NOT EXISTS integration_tokens (
          id BIGSERIAL PRIMARY KEY,
          team_id BIGINT NOT NULL,
          kind TEXT NOT NULL,
          name TEXT NOT NULL DEFAULT '',
          token TEXT NOT NULL UNIQUE,
          created_by BIGINT NULL,
          created_at TEXT NOT NULL,
          revoked_at TEXT NULL,
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
          FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS external_identities (
          id BIGSERIAL PRIMARY KEY,
          team_id BIGINT NOT NULL,
          provider TEXT NOT NULL,
          external_id TEXT NOT NULL,
          user_id BIGINT NOT NULL,
          display_name TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(team_id, provider, external_id),
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_integration_tokens_team_id ON integration_tokens(team_id)",
        "CREATE INDEX IF NOT EXISTS idx_external_identities_team_id ON external_identities(team_id)",
        "CREATE INDEX IF NOT EXISTS idx_external_identities_user_id ON external_identities(user_id)",
    ]

    for stmt in statements:
        op.execute(stmt)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for stmt in [
        "DROP TABLE IF EXISTS external_identities",
        "DROP TABLE IF EXISTS integration_tokens",
    ]:
        op.execute(stmt)

