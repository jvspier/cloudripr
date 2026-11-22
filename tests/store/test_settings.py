from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from cloudripr.store.settings import EmailSettings, ServerSettings, SettingsStore


def test_defaults() -> None:
    s = ServerSettings()
    assert s.retention_runs == 30
    assert s.idle_timeout_minutes == 30
    assert s.session_check_time == "19:00"
    assert s.gate_threshold == 100
    assert s.email == EmailSettings()
    assert s.email.smtp_host == "smtp.gmail.com"
    assert s.email.smtp_port == 587
    assert s.email.on_failure is True
    assert s.email.on_success is False


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert SettingsStore(tmp_path / "settings.toml").load() == ServerSettings()


def test_roundtrip_keeps_legacy_apprise_table(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text(
        'retention_runs = 10\n[apprise]\nurls = ["json://x"]\non_start = false\n',
        encoding="utf-8",
    )
    store = SettingsStore(path)
    s = store.load()
    assert s.apprise == {"urls": ["json://x"], "on_start": False}
    s.email.to = "me@example.com"
    store.save(s)
    again = store.load()
    assert again.apprise == {"urls": ["json://x"], "on_start": False}
    assert again.email.to == "me@example.com"
    assert again.retention_runs == 10


def test_session_check_time_validation() -> None:
    assert ServerSettings(session_check_time="").session_check_time == ""
    assert ServerSettings(session_check_time="07:05").session_check_time == "07:05"
    with pytest.raises(ValidationError):
        ServerSettings(session_check_time="25:00")
    with pytest.raises(ValidationError):
        ServerSettings(session_check_time="7pm")


def test_disabled_check_survives_save(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "s.toml")
    store.save(ServerSettings(session_check_time=""))
    assert store.load().session_check_time == ""
