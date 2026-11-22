"""Every on-disk location the app uses.

`data` is durable state worth backing up; `cache` is disposable and may be
deleted at any time (it is rebuilt).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataPaths:
    data: Path
    cache: Path

    @property
    def policies(self) -> Path:
        return self.data / "policies"

    @property
    def secrets(self) -> Path:
        return self.data / "secrets"

    @property
    def account(self) -> Path:
        return self.data / "account"

    @property
    def session(self) -> Path:
        """icloudpd --cookie-directory: the Apple session (cookies + session token)."""
        return self.data / "icloud-session"

    @property
    def app(self) -> Path:
        return self.data / "app"

    @property
    def runs(self) -> Path:
        return self.data / "runs"

    @property
    def auth_logs(self) -> Path:
        return self.data / "auth"

    @property
    def settings_file(self) -> Path:
        return self.data / "settings.toml"

    @property
    def state_db(self) -> Path:
        return self.data / "state.db"

    @property
    def hook_script(self) -> Path:
        return self.app / "bin" / "2fa-hook"

    @property
    def hook_markers(self) -> Path:
        return self.app / "markers"

    @property
    def library_db(self) -> Path:
        return self.cache / "library.db"

    def ensure(self) -> None:
        for directory in (
            self.policies,
            self.secrets,
            self.account,
            self.app,
            self.runs,
            self.auth_logs,
            self.hook_markers,
            self.hook_script.parent,
            self.cache,
            self.session,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        # Restrict access to directories holding credentials and secrets to owner only.
        # secrets: password vaults, account: user credentials, app: 2FA hook scripts,
        # session: iCloud authentication tokens. Other users must not read these.
        for credential_dir in (self.secrets, self.account, self.app, self.session):
            credential_dir.chmod(0o700)
