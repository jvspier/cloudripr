from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

from cloudripr.engine.argv import ALLOWED_ICLOUDPD_KEYS, naming_signature
from cloudripr.migration import MIGRATED_KEY, NAMING_FROZEN_KEY, NOTES_KEY, migrate
from cloudripr.paths import DataPaths
from cloudripr.runs.gate import DryRunGate
from cloudripr.store.account_store import AccountStore
from cloudripr.store.db import StateDB
from cloudripr.store.policy_store import PolicyStore
from cloudripr.store.secrets import SecretStore
from cloudripr.store.settings import SettingsStore


FIXTURE = Path(__file__).parent / "fixtures" / "policies" / "icloud.toml"
OLD_SETTINGS = """retention_runs = 10

[apprise]
urls = ["mailto://x:y@example.com"]
on_start = false
on_success = true
on_failure = true
"""


def old_data_dir(tmp_path: Path) -> DataPaths:
    """A /data directory exactly as the current app leaves it on the user's server."""
    paths = DataPaths(tmp_path / "data", tmp_path / "cache")
    paths.ensure()
    shutil.copy(FIXTURE, paths.policies / "icloud.toml")
    (paths.secrets / "icloud.password").write_text("applepw")
    paths.settings_file.write_text(OLD_SETTINGS)
    return paths


def run(paths: DataPaths) -> tuple[list[str], PolicyStore, AccountStore, DryRunGate, StateDB]:
    policies = PolicyStore(paths.policies)
    policies.load()
    db = StateDB(paths.state_db)
    accounts = AccountStore(paths.account)
    gate = DryRunGate(db)
    notes = migrate(
        paths=paths,
        policies=policies,
        secrets=SecretStore(paths.secrets),
        account_store=accounts,
        settings_store=SettingsStore(paths.settings_file),
        gate=gate,
        db=db,
    )
    return notes, policies, accounts, gate, db


def test_migrates_the_real_setup(tmp_path: Path) -> None:
    paths = old_data_dir(tmp_path)
    before = PolicyStore(paths.policies)
    before.load()
    old_policy = before.get("icloud")
    assert old_policy is not None

    notes, policies, accounts, gate, db = run(paths)

    account = accounts.load()
    assert account is not None
    assert account.apple_id == "you@example.com"
    assert account.domain == "com"
    assert accounts.password() == "applepw"
    assert (paths.secrets / "icloud.password").exists()  # kept for rollback

    new_policy = policies.get("icloud")
    assert new_policy is not None
    assert new_policy.icloudpd["cookie_directory"] == str(paths.session)
    assert naming_signature(new_policy) == naming_signature(old_policy)
    on_disk = tomllib.loads((paths.policies / "icloud.toml").read_text())
    assert on_disk["username"] == "you@example.com"  # old app needs it
    assert set(on_disk["icloudpd"]) <= ALLOWED_ICLOUDPD_KEYS  # old app accepts every key

    assert gate.state("icloud") == "armed"
    # Naming is locked from the start, not only after the first real success (final review #2).
    assert db.kv_get(NAMING_FROZEN_KEY.format(policy="icloud")) is not None

    settings = SettingsStore(paths.settings_file).load()
    assert settings.email.extra_urls == ["mailto://x:y@example.com"]
    assert settings.email.on_success is True
    assert settings.retention_runs == 30
    assert settings.apprise["urls"] == ["mailto://x:y@example.com"]  # legacy table kept

    assert any("dry run" in n for n in notes)
    assert any("No saved Apple session" in n for n in notes)
    assert db.kv_get_json(NOTES_KEY) == notes
    assert db.kv_get(MIGRATED_KEY) is not None


def test_is_idempotent(tmp_path: Path) -> None:
    paths = old_data_dir(tmp_path)
    run(paths)
    gate = DryRunGate(StateDB(paths.state_db))
    gate.clear("icloud")
    notes, *_ = run(paths)
    assert notes == []
    assert gate.state("icloud") is None  # not re-armed


def test_existing_session_is_not_flagged(tmp_path: Path) -> None:
    paths = old_data_dir(tmp_path)
    (paths.session / "youexamplecom").write_text("cookie")
    notes, *_ = run(paths)
    assert not any("No saved Apple session" in n for n in notes)


def test_fresh_install(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "data", tmp_path / "cache")
    paths.ensure()
    notes, _, accounts, _, db = run(paths)
    assert notes == []
    assert accounts.load() is None
    assert db.kv_get(MIGRATED_KEY) is not None
