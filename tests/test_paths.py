from __future__ import annotations

import stat
from pathlib import Path

from cloudripr.paths import DataPaths


def test_layout_matches_spec(tmp_path: Path) -> None:
    p = DataPaths(data=tmp_path / "data", cache=tmp_path / "cache")
    assert p.policies == tmp_path / "data" / "policies"
    assert p.secrets == tmp_path / "data" / "secrets"
    assert p.account == tmp_path / "data" / "account"
    assert p.session == tmp_path / "data" / "icloud-session"
    assert p.app == tmp_path / "data" / "app"
    assert p.runs == tmp_path / "data" / "runs"
    assert p.auth_logs == tmp_path / "data" / "auth"
    assert p.settings_file == tmp_path / "data" / "settings.toml"
    assert p.state_db == tmp_path / "data" / "state.db"
    assert p.hook_script == tmp_path / "data" / "app" / "bin" / "2fa-hook"
    assert p.hook_markers == tmp_path / "data" / "app" / "markers"
    assert p.library_db == tmp_path / "cache" / "library.db"


def test_ensure_creates_dirs_and_private_secret_dirs(tmp_path: Path) -> None:
    p = DataPaths(data=tmp_path / "data", cache=tmp_path / "cache")
    p.ensure()
    for d in (
        p.policies,
        p.secrets,
        p.account,
        p.app,
        p.runs,
        p.auth_logs,
        p.hook_markers,
        p.hook_script.parent,
        p.cache,
        p.session,
    ):
        assert d.is_dir(), d
    # Verify all four credential directories are private (owner-only)
    for secret_dir in (p.secrets, p.account, p.app, p.session):
        assert stat.S_IMODE(secret_dir.stat().st_mode) == 0o700, secret_dir
    p.ensure()  # idempotent


def test_ensure_tightens_existing_secret_dirs(tmp_path: Path) -> None:
    p = DataPaths(data=tmp_path / "data", cache=tmp_path / "cache")
    # Pre-create secrets directory with world-readable permissions
    p.secrets.mkdir(parents=True, exist_ok=True)
    p.secrets.chmod(0o755)
    assert stat.S_IMODE(p.secrets.stat().st_mode) == 0o755
    # Call ensure() which should tighten permissions
    p.ensure()
    # Verify it was restricted to owner-only
    assert stat.S_IMODE(p.secrets.stat().st_mode) == 0o700
