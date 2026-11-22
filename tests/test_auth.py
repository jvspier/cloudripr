from __future__ import annotations

import stat
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from cloudripr.auth import (
    Authenticator,
    LoginRateLimiter,
    install_session_middleware,
    load_or_create_session_key,
    require_auth,
)
from cloudripr.errors import ApiError, ValidationError, install_handlers


def test_hash_and_verify_from_env_hash() -> None:
    a = Authenticator(Authenticator.hash("hunter22"))
    assert a.needs_setup is False
    assert a.verify("hunter22")
    assert not a.verify("nope")


def test_blank_env_hash_means_setup_needed(tmp_path: Path) -> None:
    a = Authenticator("  ", hash_file=tmp_path / "login.hash")
    assert a.needs_setup is True
    assert a.current_hash is None
    assert a.verify("anything") is False


def test_malformed_or_foreign_hashes_never_verify() -> None:
    assert Authenticator("garbage").verify("x") is False
    assert Authenticator("bcrypt$salt$hash").verify("x") is False


def test_setup_writes_private_hash_file(tmp_path: Path) -> None:
    hash_file = tmp_path / "app" / "login.hash"
    a = Authenticator(None, hash_file=hash_file)
    with pytest.raises(ValidationError):
        a.setup("short")
    a.setup("long-enough")
    assert a.needs_setup is False
    assert a.verify("long-enough")
    assert stat.S_IMODE(hash_file.stat().st_mode) == 0o600
    with pytest.raises(ApiError):
        a.setup("another-one")


def test_empty_hash_file_counts_as_unset(tmp_path: Path) -> None:
    f = tmp_path / "login.hash"
    f.write_text("\n")
    assert Authenticator(None, hash_file=f).needs_setup is True


def test_setup_without_file_is_refused() -> None:
    with pytest.raises(ApiError):
        Authenticator(None).setup("long-enough")


def test_env_hash_wins_over_file(tmp_path: Path) -> None:
    f = tmp_path / "login.hash"
    f.write_text(Authenticator.hash("from-file"))
    a = Authenticator(Authenticator.hash("from-env"), hash_file=f)
    assert a.verify("from-env")
    assert not a.verify("from-file")


def test_rate_limiter_window() -> None:
    now = [0.0]
    limiter = LoginRateLimiter(max_failures=2, window=60.0, clock=lambda: now[0])
    assert limiter.allowed("ip")
    limiter.record_failure("ip")
    limiter.record_failure("ip")
    assert not limiter.allowed("ip")
    assert limiter.allowed("other")
    now[0] = 61.0
    assert limiter.allowed("ip")
    limiter.record_failure("ip")
    limiter.reset("ip")
    assert limiter.allowed("ip")


def test_session_key_created_once(tmp_path: Path) -> None:
    path = tmp_path / "app" / "session.key"
    first = load_or_create_session_key(path)
    assert load_or_create_session_key(path) == first
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    path.write_text("")
    assert load_or_create_session_key(path) != first


def _app(authenticator: Authenticator) -> FastAPI:
    app = FastAPI()
    install_handlers(app)
    install_session_middleware(app, secret="s" * 32)
    app.state.authenticator = authenticator

    @app.get("/private")
    def private(request: Request) -> dict[str, bool]:
        return {"ok": require_auth(request)}

    @app.get("/login")
    def login(request: Request) -> dict[str, bool]:
        request.session["authed"] = True
        return {"ok": True}

    return app


def test_require_auth_states(tmp_path: Path) -> None:
    setup_needed = TestClient(_app(Authenticator(None, hash_file=tmp_path / "h")))
    assert setup_needed.get("/private").json()["error"] == "Set a password first."
    client = TestClient(_app(Authenticator(Authenticator.hash("long-enough"))))
    assert client.get("/private").status_code == 401
    client.get("/login")
    assert client.get("/private").json() == {"ok": True}


def test_concurrent_setup_has_exactly_one_winner(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    hash_file = tmp_path / "login.hash"
    a = Authenticator(None, hash_file=hash_file)

    def attempt(i: int) -> int:
        try:
            a.setup(f"password-{i}")
        except ApiError as e:
            return -e.status_code
        return i

    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert sorted(r for r in results if r < 0) == [-409] * 7
    winners = [r for r in results if r >= 0]
    assert len(winners) == 1
    assert a.verify(f"password-{winners[0]}")
    assert sum(a.verify(f"password-{i}") for i in range(8)) == 1
    assert stat.S_IMODE(hash_file.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["login.hash"]


def test_setup_loses_race_to_existing_file(tmp_path: Path) -> None:
    hash_file = tmp_path / "login.hash"
    a = Authenticator(None, hash_file=hash_file)
    hash_file.write_text("")  # appears between the check and the create
    with pytest.raises(ApiError) as exc:
        Authenticator._create_exclusive(hash_file, b"x")
    assert exc.value.status_code == 409
    assert [p.name for p in tmp_path.iterdir()] == ["login.hash"]
    assert a.needs_setup is True


def test_try_acquire_is_atomic_and_prunes() -> None:
    now = [0.0]
    limiter = LoginRateLimiter(max_failures=2, window=10.0, clock=lambda: now[0])
    assert limiter.try_acquire("ip")
    assert limiter.try_acquire("ip")
    assert not limiter.try_acquire("ip")
    now[0] = 11.0
    assert limiter.allowed("ip")
    assert limiter._failures == {}
    assert limiter.try_acquire("ip")
    limiter.reset("ip")
    assert limiter._failures == {}
    limiter.record_failure("x")
    assert "x" in limiter._failures
