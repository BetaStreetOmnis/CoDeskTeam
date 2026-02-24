from __future__ import annotations

from dotenv import load_dotenv
from pathlib import Path

from .config import load_settings
from .app_factory import create_app


_REPO_ROOT = Path(__file__).resolve().parents[2]
# For local dev, prefer repo `.env` as the source of truth even if the shell already has
# exported vars (this avoids "I edited .env but it still uses the old key" surprises).
load_dotenv(dotenv_path=_REPO_ROOT / ".env", override=True)
settings = load_settings()

app = create_app(settings)
