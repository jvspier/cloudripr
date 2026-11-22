from __future__ import annotations

import stat
from pathlib import Path

import pytest
from pydantic import ValidationError

from cloudripr.store.account_store import Account, AccountStore


def test_apple_id_is_normalised() -> None:
    # Review Focus #4: icloudpd derives the session file name from --username,
    # so " Jeroen@Gmail.com " and "jeroen@gmail.com" must be the same account.
    assert Account(apple_id="  Jeroen@Gmail.COM ").apple_id == "jeroen@gmail.com"


def test_apple_id_required() -> None:
    with pytest.raises(ValidationError):
        Account(apple_id="  ")


def test_account_roundtrip(tmp_path: Path) -> None:
    store = AccountStore(tmp_path / "account")
    assert store.load() is None
    store.save(Account(apple_id="me@example.com", domain="cn"))
    assert store.load() == Account(apple_id="me@example.com", domain="cn")


def test_password_is_private(tmp_path: Path) -> None:
    store = AccountStore(tmp_path / "account")
    assert store.password() is None
    store.set_password("s3cret")
    assert store.password() == "s3cret"
    mode = stat.S_IMODE((tmp_path / "account" / "apple.password").stat().st_mode)
    assert mode == 0o600


def test_library_cache(tmp_path: Path) -> None:
    store = AccountStore(tmp_path / "account")
    assert store.library("shared") is None
    store.set_library("shared", "SharedSync-ABC")
    assert AccountStore(tmp_path / "account").library("shared") == "SharedSync-ABC"
    store.clear_library("shared")
    assert store.library("shared") is None
