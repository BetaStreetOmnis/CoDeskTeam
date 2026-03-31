from __future__ import annotations

from pathlib import Path

from jetlinks_ai_api.config import _maybe_migrate_legacy_runtime, _pick_default_data_dir


def test_pick_default_data_dir_prefers_migrated_primary(tmp_path: Path) -> None:
    legacy = tmp_path / ".aistaff"
    primary = tmp_path / ".jetlinks-ai"
    (legacy / "outputs").mkdir(parents=True)
    (legacy / "aistaff.db").write_text("legacy-db", encoding="utf-8")
    (legacy / "jwt_secret").write_text("legacy-secret", encoding="utf-8")
    (legacy / "shared_invite_token").write_text("legacy-token", encoding="utf-8")
    (legacy / "outputs" / "sample.txt").write_text("artifact", encoding="utf-8")

    chosen = _pick_default_data_dir(tmp_path)

    assert chosen == primary
    assert (primary / "jetlinks_ai.db").read_text(encoding="utf-8") == "legacy-db"
    assert (primary / "jwt_secret").read_text(encoding="utf-8") == "legacy-secret"
    assert (primary / "shared_invite_token").read_text(encoding="utf-8") == "legacy-token"
    assert (primary / "outputs" / "sample.txt").read_text(encoding="utf-8") == "artifact"


def test_pick_default_data_dir_keeps_legacy_when_migrate_disabled(tmp_path: Path) -> None:
    legacy = tmp_path / ".aistaff"
    primary = tmp_path / ".jetlinks-ai"
    legacy.mkdir(parents=True)
    (legacy / "aistaff.db").write_text("legacy-db", encoding="utf-8")

    chosen = _pick_default_data_dir(tmp_path, allow_migrate=False)

    assert chosen == legacy
    assert not (primary / "jetlinks_ai.db").exists()


def test_maybe_migrate_legacy_runtime_is_noop_when_primary_exists(tmp_path: Path) -> None:
    legacy = tmp_path / ".aistaff"
    primary = tmp_path / ".jetlinks-ai"
    legacy.mkdir(parents=True)
    primary.mkdir(parents=True)
    (legacy / "aistaff.db").write_text("legacy-db", encoding="utf-8")
    (primary / "jetlinks_ai.db").write_text("primary-db", encoding="utf-8")

    _maybe_migrate_legacy_runtime(tmp_path)

    assert (primary / "jetlinks_ai.db").read_text(encoding="utf-8") == "primary-db"
