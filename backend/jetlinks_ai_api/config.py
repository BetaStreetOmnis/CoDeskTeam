from __future__ import annotations

import os
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

from .env_utils import env_bool, env_int, env_str


def _raw_env_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _read_text_if_exists(path: Path) -> str | None:
    try:
        if not path.exists():
            return None
        value = path.read_text(encoding="utf-8").strip()
        return value or None
    except Exception:
        return None


@dataclass(frozen=True)
class Settings:
    app_root: Path
    provider: str
    model: str
    openai_api_key: str | None
    openai_base_url: str
    openai_verify_ssl: bool
    openai_image_model: str
    glm_api_key: str | None
    glm_base_url: str
    glm_model: str
    glm_image_model: str
    public_base_url: str
    public_demo_enabled: bool
    public_demo_route: str
    public_demo_team_name: str
    public_demo_user_email: str
    public_demo_user_name: str
    public_demo_auth_window_seconds: int
    public_demo_auth_max_requests: int
    public_demo_write_window_seconds: int
    public_demo_write_max_requests: int
    public_demo_upload_window_seconds: int
    public_demo_upload_max_requests: int
    public_demo_pipeline_window_seconds: int
    public_demo_pipeline_max_requests: int
    public_demo_audit_enabled: bool
    public_demo_audit_log_path: Path
    workspace_root: Path
    projects_roots: list[Path]
    workspace_layout: str
    workspace_user_dir: str
    super_emails: frozenset[str]
    super_all: bool
    db_url: str | None
    outputs_dir: Path
    data_dir: Path
    db_path: Path
    jwt_secret: str
    jwt_exp_minutes: int
    shared_invite_token: str | None
    enable_shell: bool
    enable_write: bool
    enable_browser: bool
    max_steps: int
    max_tool_output_chars: int
    max_file_read_chars: int
    session_ttl_minutes: int
    max_sessions: int
    max_session_messages: int
    max_context_chars: int
    outputs_ttl_hours: int
    max_browser_pages: int
    browser_page_ttl_minutes: int
    codex_command: str
    codex_timeout_seconds: int
    codex_reasoning_effort: str
    codex_allow_dangerous: bool
    claude_command: str
    claude_timeout_seconds: int
    claude_model: str
    opencode_base_url: str
    opencode_username: str
    opencode_password: str | None
    opencode_timeout_seconds: int
    nanobot_command: str
    nanobot_home_dir: Path
    nanobot_timeout_seconds: int
    cors_origins: list[str]
    feishu_preset_name: str | None
    feishu_preset_webhook_url: str | None
    feishu_preset_verification_token: str | None
    feishu_preset_enabled: bool
    enable_pi: bool
    pi_backend: str
    pi_docker_image: str
    pi_timeout_seconds: int
    pi_mono_dir: Path
    pi_agent_dir: Path
    pi_enable_tools: bool
    openclaw_enabled: bool
    openclaw_embedded: bool
    openclaw_command: str
    openclaw_gateway_command: str | None
    openclaw_gateway_base_url: str
    openclaw_gateway_port: int
    openclaw_gateway_bind: str
    openclaw_working_dir: Path
    openclaw_timeout_seconds: int


def _copy_if_missing(src: Path, dst: Path) -> None:
    if not src.exists() or dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)



def _copy_tree_if_missing(src: Path, dst: Path) -> None:
    if not src.exists() or dst.exists():
        return
    shutil.copytree(src, dst)



def _maybe_migrate_legacy_runtime(repo_root: Path) -> None:
    primary = repo_root / ".jetlinks-ai"
    legacy = repo_root / ".aistaff"
    primary_db = primary / "jetlinks_ai.db"
    legacy_db = legacy / "aistaff.db"

    if primary_db.exists() or not legacy_db.exists():
        return

    primary.mkdir(parents=True, exist_ok=True)
    _copy_if_missing(legacy_db, primary_db)
    _copy_if_missing(legacy / "jwt_secret", primary / "jwt_secret")
    _copy_if_missing(legacy / "shared_invite_token", primary / "shared_invite_token")
    _copy_if_missing(legacy / "chatbi_demo.db", primary / "chatbi_demo.db")

    for name in ["outputs", "history_sessions", "tasks", "pi", "nanobot-home"]:
        _copy_tree_if_missing(legacy / name, primary / name)

    if primary_db.exists():
        print(f"[jetlinks-ai] 已从旧目录迁移运行数据：{legacy} -> {primary}")



def _pick_default_data_dir(repo_root: Path, *, allow_migrate: bool = True) -> Path:
    primary = repo_root / ".jetlinks-ai"
    legacy = repo_root / ".aistaff"

    if allow_migrate:
        _maybe_migrate_legacy_runtime(repo_root)

    if (primary / "jetlinks_ai.db").exists():
        return primary
    if (legacy / "aistaff.db").exists():
        return legacy
    return primary


def load_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    workspace_root = Path(env_str("WORKSPACE", str(repo_root)) or str(repo_root)).resolve()
    workspace_layout = (env_str("WORKSPACE_LAYOUT", "shared") or "shared").strip().lower()
    if workspace_layout not in {"shared", "per_user"}:
        workspace_layout = "shared"
    workspace_user_dir = (env_str("WORKSPACE_USER_DIR", "users") or "users").strip().strip("/\\")
    if not workspace_user_dir or ".." in workspace_user_dir:
        workspace_user_dir = "users"
    projects_roots = [
        Path(p.strip()).expanduser().resolve()
        for p in (env_str("PROJECTS_ROOT", str(workspace_root)) or str(workspace_root)).split(",")
        if p.strip()
    ]
    if not projects_roots:
        projects_roots = [workspace_root]

    data_dir_raw = env_str("DATA_DIR", None)
    explicit_db_path = env_str("DB_PATH", None)
    explicit_outputs_dir = env_str("OUTPUTS_DIR", None)
    allow_runtime_migrate = not explicit_db_path and not explicit_outputs_dir
    data_dir = (
        Path(data_dir_raw).expanduser().resolve()
        if data_dir_raw
        else _pick_default_data_dir(repo_root, allow_migrate=allow_runtime_migrate).resolve()
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir = Path(env_str("OUTPUTS_DIR", str(data_dir / "outputs")) or str(data_dir / "outputs")).resolve()

    db_url = (env_str("DB_URL", "") or "").strip() or None
    default_db_filename = "aistaff.db" if data_dir.name == ".aistaff" else "jetlinks_ai.db"
    default_db_path = data_dir / default_db_filename
    db_path = Path(env_str("DB_PATH", str(default_db_path)) or str(default_db_path)).resolve()

    jwt_secret = env_str("JWT_SECRET", None)
    if not jwt_secret:
        secret_path = data_dir / "jwt_secret"
        jwt_secret = _read_text_if_exists(secret_path)
        if not jwt_secret:
            jwt_secret = secrets.token_urlsafe(48)
            secret_path.write_text(jwt_secret, encoding="utf-8")

    jwt_exp_minutes = env_int("JWT_EXP_MINUTES", 7 * 24 * 60)

    shared_invite_token = (env_str("SHARED_INVITE_TOKEN", "") or "").strip() or None
    if not shared_invite_token:
        auto_shared = env_bool("SHARED_INVITE_AUTO", True)
        if auto_shared:
            token_path = data_dir / "shared_invite_token"
            shared_invite_token = _read_text_if_exists(token_path)
            if not shared_invite_token:
                shared_invite_token = secrets.token_urlsafe(24)
                token_path.write_text(shared_invite_token, encoding="utf-8")
                print(f"[jetlinks-ai] 已生成通用邀请码（内部使用）并写入：{token_path}")

    cors_origins = [
        origin.strip()
        for origin in (env_str("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173") or "").split(
            ","
        )
        if origin.strip()
    ]

    public_base_url = (env_str("PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    public_demo_route = (env_str("PUBLIC_DEMO_ROUTE", "/demo") or "/demo").strip()
    if not public_demo_route.startswith("/"):
        public_demo_route = f"/{public_demo_route}"
    public_demo_route = "/" + public_demo_route.strip().strip("/")
    if public_demo_route == "/":
        public_demo_route = "/demo"
    public_demo_audit_log_path = Path(
        env_str("PUBLIC_DEMO_AUDIT_LOG_PATH", str(data_dir / "logs" / "public_demo_audit.jsonl"))
        or str(data_dir / "logs" / "public_demo_audit.jsonl")
    ).expanduser().resolve()
    super_emails_raw = env_str("SUPER_EMAILS", "") or ""
    super_emails = frozenset(
        email.strip().lower() for email in super_emails_raw.split(",") if email.strip()
    )

    pi_mono_dir = Path(env_str("PI_MONO_DIR", str(repo_root / "third_party" / "pi-mono"))).expanduser().resolve()
    pi_agent_dir = Path(env_str("PI_AGENT_DIR", str(data_dir / "pi" / "agent"))).expanduser().resolve()
    pi_backend = (env_str("PI_BACKEND", "auto") or "auto").strip().lower()
    if pi_backend not in {"auto", "local", "docker"}:
        pi_backend = "auto"

    return Settings(
        app_root=repo_root,
        provider=env_str("PROVIDER", "openai") or "openai",
        model=env_str("MODEL", "gpt-5.2") or "gpt-5.2",
        openai_api_key=_raw_env_str("OPENAI_API_KEY", None),
        openai_base_url=_raw_env_str("OPENAI_BASE_URL", "https://api.openai.com/v1") or "https://api.openai.com/v1",
        openai_verify_ssl=env_bool("OPENAI_VERIFY_SSL", True),
        openai_image_model=env_str("OPENAI_IMAGE_MODEL", "gpt-image-1") or "gpt-image-1",
        glm_api_key=_raw_env_str("GLM_API_KEY", None),
        glm_base_url=_raw_env_str("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4") or "https://open.bigmodel.cn/api/paas/v4",
        glm_model=env_str("GLM_MODEL", "glm-4.5") or "glm-4.5",
        glm_image_model=env_str("GLM_IMAGE_MODEL", "cogview-3-flash") or "cogview-3-flash",
        public_base_url=public_base_url,
        public_demo_enabled=env_bool("PUBLIC_DEMO_ENABLED", False),
        public_demo_route=public_demo_route,
        public_demo_team_name=env_str("PUBLIC_DEMO_TEAM_NAME", "公开演示团队") or "公开演示团队",
        public_demo_user_email=env_str("PUBLIC_DEMO_USER_EMAIL", "demo@jetlinks.local") or "demo@jetlinks.local",
        public_demo_user_name=env_str("PUBLIC_DEMO_USER_NAME", "Demo Visitor") or "Demo Visitor",
        public_demo_auth_window_seconds=env_int("PUBLIC_DEMO_AUTH_WINDOW_SECONDS", 300),
        public_demo_auth_max_requests=env_int("PUBLIC_DEMO_AUTH_MAX_REQUESTS", 20),
        public_demo_write_window_seconds=env_int("PUBLIC_DEMO_WRITE_WINDOW_SECONDS", 300),
        public_demo_write_max_requests=env_int("PUBLIC_DEMO_WRITE_MAX_REQUESTS", 30),
        public_demo_upload_window_seconds=env_int("PUBLIC_DEMO_UPLOAD_WINDOW_SECONDS", 600),
        public_demo_upload_max_requests=env_int("PUBLIC_DEMO_UPLOAD_MAX_REQUESTS", 12),
        public_demo_pipeline_window_seconds=env_int("PUBLIC_DEMO_PIPELINE_WINDOW_SECONDS", 600),
        public_demo_pipeline_max_requests=env_int("PUBLIC_DEMO_PIPELINE_MAX_REQUESTS", 12),
        public_demo_audit_enabled=env_bool("PUBLIC_DEMO_AUDIT_ENABLED", True),
        public_demo_audit_log_path=public_demo_audit_log_path,
        workspace_root=workspace_root,
        projects_roots=projects_roots,
        workspace_layout=workspace_layout,
        workspace_user_dir=workspace_user_dir,
        super_emails=super_emails,
        super_all=env_bool("SUPER_ALL", False),
        db_url=db_url,
        outputs_dir=outputs_dir,
        data_dir=data_dir,
        db_path=db_path,
        jwt_secret=jwt_secret,
        jwt_exp_minutes=jwt_exp_minutes,
        shared_invite_token=shared_invite_token,
        enable_shell=env_bool("ENABLE_SHELL", False),
        enable_write=env_bool("ENABLE_WRITE", False),
        enable_browser=env_bool("ENABLE_BROWSER", False),
        max_steps=env_int("MAX_STEPS", 10),
        max_tool_output_chars=env_int("MAX_TOOL_OUTPUT_CHARS", 12_000),
        max_file_read_chars=env_int("MAX_FILE_READ_CHARS", 120_000),
        session_ttl_minutes=env_int("SESSION_TTL_MINUTES", 120),
        max_sessions=env_int("MAX_SESSIONS", 200),
        max_session_messages=env_int("MAX_SESSION_MESSAGES", 120),
        max_context_chars=env_int("MAX_CONTEXT_CHARS", 120_000),
        outputs_ttl_hours=env_int("OUTPUTS_TTL_HOURS", 7 * 24),
        max_browser_pages=env_int("MAX_BROWSER_PAGES", 8),
        browser_page_ttl_minutes=env_int("BROWSER_PAGE_TTL_MINUTES", 30),
        codex_command=env_str("CODEX_CMD", "codex") or "codex",
        codex_timeout_seconds=env_int("CODEX_TIMEOUT_SECONDS", 300),
        codex_reasoning_effort=env_str("CODEX_REASONING_EFFORT", "medium") or "medium",
        codex_allow_dangerous=env_bool("CODEX_ALLOW_DANGEROUS", False),
        claude_command=env_str("CLAUDE_CMD", "/usr/local/bin/claude-host") or "/usr/local/bin/claude-host",
        claude_timeout_seconds=env_int("CLAUDE_TIMEOUT_SECONDS", 300),
        claude_model=env_str("CLAUDE_MODEL", "glm-4.7") or "glm-4.7",
        opencode_base_url=env_str("OPENCODE_BASE_URL", "http://127.0.0.1:4096") or "http://127.0.0.1:4096",
        opencode_username=env_str("OPENCODE_USERNAME", "opencode") or "opencode",
        opencode_password=env_str("OPENCODE_PASSWORD", None),
        opencode_timeout_seconds=env_int("OPENCODE_TIMEOUT_SECONDS", 300),
        nanobot_command=env_str("NANOBOT_CMD", "nanobot") or "nanobot",
        nanobot_home_dir=Path(
            env_str("NANOBOT_HOME", str(data_dir / "nanobot-home")) or str(data_dir / "nanobot-home")
        )
        .expanduser()
        .resolve(),
        nanobot_timeout_seconds=env_int("NANOBOT_TIMEOUT_SECONDS", 300),
        cors_origins=cors_origins,
        feishu_preset_name=env_str("FEISHU_PRESET_NAME", None),
        feishu_preset_webhook_url=env_str("FEISHU_PRESET_WEBHOOK_URL", None),
        feishu_preset_verification_token=env_str("FEISHU_PRESET_VERIFICATION_TOKEN", None),
        feishu_preset_enabled=env_bool("FEISHU_PRESET_ENABLED", True),
        enable_pi=env_bool("ENABLE_PI", False),
        pi_backend=pi_backend,
        pi_docker_image=env_str("PI_DOCKER_IMAGE", "node:20") or "node:20",
        pi_timeout_seconds=env_int("PI_TIMEOUT_SECONDS", 300),
        pi_mono_dir=pi_mono_dir,
        pi_agent_dir=pi_agent_dir,
        pi_enable_tools=env_bool("PI_ENABLE_TOOLS", False),
        openclaw_enabled=env_bool("ENABLE_OPENCLAW", True),
        openclaw_embedded=env_bool("OPENCLAW_EMBEDDED", False),
        openclaw_command=env_str("OPENCLAW_CMD", "openclaw") or "openclaw",
        openclaw_gateway_command=env_str("OPENCLAW_GATEWAY_CMD", None),
        openclaw_gateway_base_url=(
            env_str("OPENCLAW_GATEWAY_BASE_URL", "http://127.0.0.1:18789") or "http://127.0.0.1:18789"
        ).strip().rstrip("/"),
        openclaw_gateway_port=env_int("OPENCLAW_GATEWAY_PORT", 18789),
        openclaw_gateway_bind=env_str("OPENCLAW_GATEWAY_BIND", "loopback") or "loopback",
        openclaw_working_dir=Path(
            env_str("OPENCLAW_WORKDIR", str(repo_root / "third_party" / "openclaw"))
            or str(repo_root / "third_party" / "openclaw")
        )
        .expanduser()
        .resolve(),
        openclaw_timeout_seconds=env_int("OPENCLAW_TIMEOUT_SECONDS", 300),
    )
