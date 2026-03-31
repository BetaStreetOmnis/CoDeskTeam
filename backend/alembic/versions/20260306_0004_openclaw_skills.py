from __future__ import annotations

from alembic import op

revision = "20260306_0004"
down_revision = "20260221_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS openclaw_sessions (
          id BIGSERIAL PRIMARY KEY,
          team_id BIGINT NOT NULL,
          user_id BIGINT NOT NULL,
          chat_session_id TEXT NOT NULL,
          openclaw_session_id TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(team_id, chat_session_id),
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY (chat_session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS openclaw_channels (
          id BIGSERIAL PRIMARY KEY,
          team_id BIGINT NOT NULL,
          channel_key TEXT NOT NULL,
          channel_type TEXT NOT NULL DEFAULT '',
          external_id TEXT NOT NULL DEFAULT '',
          name TEXT NOT NULL DEFAULT '',
          enabled INTEGER NOT NULL DEFAULT 1,
          meta_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(team_id, channel_key),
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS openclaw_plugins (
          id BIGSERIAL PRIMARY KEY,
          team_id BIGINT NOT NULL,
          plugin_key TEXT NOT NULL,
          name TEXT NOT NULL DEFAULT '',
          version TEXT NOT NULL DEFAULT '',
          source TEXT NOT NULL DEFAULT '',
          enabled INTEGER NOT NULL DEFAULT 1,
          meta_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(team_id, plugin_key),
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS openclaw_skills (
          id BIGSERIAL PRIMARY KEY,
          team_id BIGINT NOT NULL,
          skill_key TEXT NOT NULL,
          name TEXT NOT NULL DEFAULT '',
          description TEXT NOT NULL DEFAULT '',
          entrypoint TEXT NOT NULL DEFAULT '',
          enabled INTEGER NOT NULL DEFAULT 1,
          meta_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(team_id, skill_key),
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_openclaw_sessions_team_chat ON openclaw_sessions(team_id, chat_session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_openclaw_channels_team ON openclaw_channels(team_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_openclaw_plugins_team ON openclaw_plugins(team_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_openclaw_skills_team ON openclaw_skills(team_id)")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TABLE IF EXISTS openclaw_skills")
    op.execute("DROP TABLE IF EXISTS openclaw_plugins")
    op.execute("DROP TABLE IF EXISTS openclaw_channels")
    op.execute("DROP TABLE IF EXISTS openclaw_sessions")
