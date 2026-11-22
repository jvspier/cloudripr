from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from cloudripr import cli


def test_help_runs() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "cloudripr", "--help"], capture_output=True, text=True
    )
    assert r.returncode == 0
    assert "--cache-dir" in r.stdout


def test_init_password_hashes() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "cloudripr", "init-password", "hunter22"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert r.stdout.strip().startswith("scrypt$")


def test_main_builds_app_with_persistent_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: calls.append({"app": app, **kw}))
    data, cache = tmp_path / "data", tmp_path / "cache"
    assert (
        cli.main(
            [
                "--data-dir",
                str(data),
                "--cache-dir",
                str(cache),
                "--host",
                "0.0.0.0",
                "--port",
                "5001",
            ]
        )
        == 0
    )
    assert calls[0]["host"] == "0.0.0.0"
    assert calls[0]["port"] == 5001
    assert (data / "app" / "session.key").is_file()
    assert cache.is_dir()
    assert calls[0]["app"].state.authenticator.needs_setup is True


def test_cache_dir_defaults_inside_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: None)
    monkeypatch.delenv("CACHE_DIR", raising=False)
    cli.main(["--data-dir", str(tmp_path / "data")])
    assert (tmp_path / "data" / "cache").is_dir()


def test_engine_command_override_for_development(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: None)
    monkeypatch.setattr("cloudripr.app.create_app", lambda **kw: seen.update(kw) or object())
    monkeypatch.setenv("CLOUDRIPR_ICLOUDPD_CMD", "python3 tests/fixtures/icloudpd_sim.py")
    cli.main(["--data-dir", str(tmp_path / "data")])
    assert seen["icloudpd_cmd"] == ["python3", "tests/fixtures/icloudpd_sim.py"]


def test_engine_command_defaults_to_icloudpd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: None)
    monkeypatch.setattr("cloudripr.app.create_app", lambda **kw: seen.update(kw) or object())
    monkeypatch.delenv("CLOUDRIPR_ICLOUDPD_CMD", raising=False)
    cli.main(["--data-dir", str(tmp_path / "data")])
    assert seen["icloudpd_cmd"] == ["icloudpd"]
