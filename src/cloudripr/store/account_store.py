"""The single iCloud account: Apple ID, password, library cache."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

import tomli_w
from pydantic import BaseModel, field_validator

from cloudripr.store.fileio import write_atomic


class Account(BaseModel):
    apple_id: str
    domain: Literal["com", "cn"] = "com"

    @field_validator("apple_id")
    @classmethod
    def _normalise(cls, v: str) -> str:
        # icloudpd names the session file after --username; Apple IDs are
        # case-insensitive, so normalise to keep finding the same session.
        v = v.strip().lower()
        if len(v) < 3:
            raise ValueError("Enter your Apple ID (email address).")
        return v


class AccountStore:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def _account_file(self) -> Path:
        return self._dir / "account.toml"

    @property
    def _password_file(self) -> Path:
        return self._dir / "apple.password"

    @property
    def _library_file(self) -> Path:
        return self._dir / "library.toml"

    def load(self) -> Account | None:
        if not self._account_file.is_file():
            return None
        return Account(**tomllib.loads(self._account_file.read_text(encoding="utf-8")))

    def save(self, account: Account) -> None:
        write_atomic(self._account_file, tomli_w.dumps(account.model_dump()).encode("utf-8"))

    def password(self) -> str | None:
        if not self._password_file.is_file():
            return None
        return self._password_file.read_text(encoding="utf-8") or None

    def set_password(self, value: str) -> None:
        write_atomic(self._password_file, value.encode("utf-8"), mode=0o600)

    def _libraries(self) -> dict[str, str]:
        if not self._library_file.is_file():
            return {}
        return dict(tomllib.loads(self._library_file.read_text(encoding="utf-8")))

    def library(self, kind: str) -> str | None:
        return self._libraries().get(kind)

    def set_library(self, kind: str, ident: str) -> None:
        data = self._libraries()
        data[kind] = ident
        write_atomic(self._library_file, tomli_w.dumps(data).encode("utf-8"))

    def clear_library(self, kind: str) -> None:
        data = self._libraries()
        data.pop(kind, None)
        write_atomic(self._library_file, tomli_w.dumps(data).encode("utf-8"))
