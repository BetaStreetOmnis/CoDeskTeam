"""init schema (postgres)

Revision ID: 20260220_0001
Revises:
Create Date: 2026-02-20
"""

from __future__ import annotations

from alembic import op


revision = "20260220_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    statements = [
        """
        CREATE TABLE IF NOT EXISTS meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
          id BIGSERIAL PRIMARY KEY,
          email TEXT NOT NULL UNIQUE,
          name TEXT NOT NULL,
          password_hash TEXT NOT NULL,
          created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS teams (
          id BIGSERIAL PRIMARY KEY,
          name TEXT NOT NULL,
          created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS memberships (
          user_id BIGINT NOT NULL,
          team_id BIGINT NOT NULL,
          role TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY (user_id, team_id),
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS team_skills (
          id BIGSERIAL PRIMARY KEY,
          team_id BIGINT NOT NULL,
          name TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          content TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS invites (
          id BIGSERIAL PRIMARY KEY,
          team_id BIGINT NOT NULL,
          email TEXT NULL,
          role TEXT NOT NULL,
          token TEXT NOT NULL UNIQUE,
          created_by BIGINT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          used_at TEXT NULL,
          used_by BIGINT NULL,
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
          FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
          FOREIGN KEY (used_by) REFERENCES users(id) ON DELETE SET NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS team_projects (
          id BIGSERIAL PRIMARY KEY,
          team_id BIGINT NOT NULL,
          name TEXT NOT NULL,
          slug TEXT NOT NULL,
          path TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(team_id, slug),
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS team_requirements (
          id BIGSERIAL PRIMARY KEY,
          team_id BIGINT NOT NULL,
          project_id BIGINT NULL,
          source_team TEXT NOT NULL DEFAULT '',
          title TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'incoming',
          priority TEXT NOT NULL DEFAULT 'medium',
          delivery_from_team_id BIGINT NULL,
          delivery_by_user_id BIGINT NULL,
          delivery_state TEXT NOT NULL DEFAULT '',
          delivery_decided_by_user_id BIGINT NULL,
          delivery_decided_at TEXT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
          FOREIGN KEY (project_id) REFERENCES team_projects(id) ON DELETE SET NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS team_settings (
          team_id BIGINT PRIMARY KEY,
          workspace_path TEXT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS team_chatbi_datasources (
          id BIGSERIAL PRIMARY KEY,
          team_id BIGINT NOT NULL,
          datasource_id TEXT NOT NULL,
          name TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          db_type TEXT NOT NULL DEFAULT 'sqlite',
          db_path TEXT NOT NULL DEFAULT '',
          db_url TEXT NOT NULL DEFAULT '',
          tables_json TEXT NOT NULL DEFAULT '[]',
          enabled INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(team_id, datasource_id),
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wecom_apps (
          id BIGSERIAL PRIMARY KEY,
          team_id BIGINT NOT NULL,
          name TEXT NOT NULL,
          hook TEXT NOT NULL UNIQUE,
          corp_id TEXT NOT NULL,
          agent_id BIGINT NOT NULL,
          corp_secret TEXT NOT NULL,
          token TEXT NOT NULL,
          encoding_aes_key TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS feishu_webhooks (
          id BIGSERIAL PRIMARY KEY,
          team_id BIGINT NOT NULL,
          name TEXT NOT NULL,
          hook TEXT NOT NULL UNIQUE,
          webhook_url TEXT NOT NULL,
          verification_token TEXT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
          session_id TEXT PRIMARY KEY,
          team_id BIGINT NOT NULL,
          user_id BIGINT NOT NULL,
          role TEXT NOT NULL,
          provider TEXT NOT NULL,
          model TEXT NOT NULL,
          project_id BIGINT NULL,
          title TEXT NOT NULL DEFAULT '',
          opencode_session_id TEXT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY (project_id) REFERENCES team_projects(id) ON DELETE SET NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
          id BIGSERIAL PRIMARY KEY,
          session_id TEXT NOT NULL,
          team_id BIGINT NOT NULL,
          user_id BIGINT NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          attachments_json TEXT NOT NULL DEFAULT '[]',
          events_json TEXT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS file_records (
          file_id TEXT PRIMARY KEY,
          team_id BIGINT NOT NULL,
          user_id BIGINT NOT NULL,
          project_id BIGINT NULL,
          session_id TEXT NULL,
          kind TEXT NOT NULL,
          filename TEXT NOT NULL,
          content_type TEXT NOT NULL,
          size_bytes BIGINT NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY (project_id) REFERENCES team_projects(id) ON DELETE SET NULL,
          FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE SET NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_team_skills_team_id ON team_skills(team_id)",
        "CREATE INDEX IF NOT EXISTS idx_memberships_team_id ON memberships(team_id)",
        "CREATE INDEX IF NOT EXISTS idx_invites_team_id ON invites(team_id)",
        "CREATE INDEX IF NOT EXISTS idx_invites_token ON invites(token)",
        "CREATE INDEX IF NOT EXISTS idx_team_projects_team_id ON team_projects(team_id)",
        "CREATE INDEX IF NOT EXISTS idx_team_requirements_team_id ON team_requirements(team_id)",
        "CREATE INDEX IF NOT EXISTS idx_team_requirements_project_id ON team_requirements(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_team_chatbi_datasources_team_id ON team_chatbi_datasources(team_id)",
        "CREATE INDEX IF NOT EXISTS idx_wecom_apps_team_id ON wecom_apps(team_id)",
        "CREATE INDEX IF NOT EXISTS idx_wecom_apps_hook ON wecom_apps(hook)",
        "CREATE INDEX IF NOT EXISTS idx_feishu_webhooks_team_id ON feishu_webhooks(team_id)",
        "CREATE INDEX IF NOT EXISTS idx_feishu_webhooks_hook ON feishu_webhooks(hook)",
        "CREATE INDEX IF NOT EXISTS idx_chat_sessions_team_user_updated ON chat_sessions(team_id, user_id, updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id, id)",
        "CREATE INDEX IF NOT EXISTS idx_file_records_team_user_created ON file_records(team_id, user_id, created_at)",
    ]

    for stmt in statements:
        op.execute(stmt)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    # Production does not rely on downgrade paths today; keep it conservative.
    for stmt in [
        "DROP TABLE IF EXISTS file_records",
        "DROP TABLE IF EXISTS chat_messages",
        "DROP TABLE IF EXISTS chat_sessions",
        "DROP TABLE IF EXISTS feishu_webhooks",
        "DROP TABLE IF EXISTS wecom_apps",
        "DROP TABLE IF EXISTS team_chatbi_datasources",
        "DROP TABLE IF EXISTS team_settings",
        "DROP TABLE IF EXISTS team_requirements",
        "DROP TABLE IF EXISTS team_projects",
        "DROP TABLE IF EXISTS invites",
        "DROP TABLE IF EXISTS team_skills",
        "DROP TABLE IF EXISTS memberships",
        "DROP TABLE IF EXISTS teams",
        "DROP TABLE IF EXISTS users",
        "DROP TABLE IF EXISTS meta",
    ]:
        op.execute(stmt)

