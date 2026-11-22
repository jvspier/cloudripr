from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from cloudripr.account.reauth import AttemptError, ReauthAttempt
from cloudripr.account.service import (
    AccountNotConfigured,
    AccountService,
    AccountState,
    RunInProgress,
)
from cloudripr.engine.lock import AccountLock
from tests.helpers import build_account_stack, eventually


async def test_state_defaults_and_persists(tmp_path: Path) -> None:
    s = build_account_stack(tmp_path)
    assert s.account.state().state == "unknown"
    s.account.mark_ok()
    st = s.account.state()
    assert st.state == "ok"
    assert st.last_verified_at is not None
    again = AccountService(
        paths=s.paths,
        store=s.store,
        db=s.db,
        lock=s.lock,
        bus=s.bus,
        notifier=s.notifier,
        icloudpd_cmd=[],
        idle_timeout=lambda: 1.0,
    )
    assert again.state().state == "ok"


async def test_needs_reauth_emails_once_and_ok_clears_reminder(tmp_path: Path) -> None:
    s = build_account_stack(tmp_path)
    s.account.mark_needs_reauth("Apple asked for a new sign-in.")
    s.account.mark_needs_reauth("again")
    await eventually(lambda: len(s.sender.calls) == 1)
    await asyncio.sleep(0.1)
    assert s.sender.titles == ["iCloud needs you to sign in again"]
    assert s.account.state().reason == "Apple asked for a new sign-in."
    s.account.mark_ok()
    assert s.db.kv_get("reauth_email_at") is None


async def test_reauth_success_runs_catch_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    s = build_account_stack(tmp_path)
    s.account.mark_needs_reauth("expired")
    caught_up: list[bool] = []

    async def catch_up() -> None:
        caught_up.append(True)

    s.account.on_reauth_success = catch_up
    attempt = await s.account.start_reauth()
    assert await s.account.start_reauth() is attempt  # idempotent while active
    await eventually(lambda: attempt.state == "awaiting_code")
    assert s.account.state().state == "reauthenticating"
    await s.account.submit_code("123456")
    await s.account.wait_attempt()
    assert s.account.state().state == "ok"
    assert caught_up == [True]
    record = s.db.get_attempt(attempt.id)
    assert record is not None
    assert record.outcome == "succeeded"


async def test_failed_reauth_restores_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    s = build_account_stack(tmp_path)
    s.account.mark_needs_reauth("expired")
    attempt = await s.account.start_reauth()
    await eventually(lambda: attempt.state == "awaiting_code")
    await s.account.submit_code("000000")
    await s.account.wait_attempt()
    assert attempt.state == "rejected"
    assert s.account.state().state == "needs_reauth"


async def test_refused_while_a_run_holds_the_lock(tmp_path: Path) -> None:
    s = build_account_stack(tmp_path)
    release = asyncio.Event()

    async def run() -> None:
        async with s.lock.hold(AccountLock.RUN, "run:icloud"):
            await release.wait()

    task = asyncio.create_task(run())
    await asyncio.sleep(0)
    with pytest.raises(RunInProgress) as exc:
        await s.account.start_reauth()
    assert exc.value.policy == "icloud"
    release.set()
    await task


async def test_restart_gives_a_new_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    s = build_account_stack(tmp_path)
    first = await s.account.start_reauth()
    await eventually(lambda: first.state == "awaiting_code")
    second = await s.account.restart_reauth()
    assert second.id != first.id
    assert first.state == "cancelled"
    await eventually(lambda: second.state == "awaiting_code")
    await s.account.cancel_reauth()
    assert second.state == "cancelled"


async def test_not_configured(tmp_path: Path) -> None:
    s = build_account_stack(tmp_path, configured=False)
    with pytest.raises(AccountNotConfigured):
        await s.account.start_reauth()
    assert await s.account.check_session() == "not_configured"


async def test_submit_without_attempt(tmp_path: Path) -> None:
    s = build_account_stack(tmp_path)
    with pytest.raises(AttemptError):
        await s.account.submit_code("123456")


async def test_check_session_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "ok")
    s = build_account_stack(tmp_path)
    assert await s.account.check_session() == "ok"
    assert s.account.state().state == "ok"


async def test_check_session_flags_expiry_without_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    s = build_account_stack(tmp_path)
    assert await s.account.check_session() == "needs_reauth"
    assert s.account.state().state == "needs_reauth"
    log_text = (s.paths.auth_logs / "session-check.log").read_text()
    assert "Please enter" not in log_text
    await eventually(lambda: s.sender.titles == ["iCloud needs you to sign in again"])


async def test_check_session_skipped_when_already_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv_out = tmp_path / "argv.jsonl"
    monkeypatch.setenv("ICLOUDPD_SIM_ARGV_OUT", str(argv_out))
    s = build_account_stack(tmp_path)
    s.account.mark_needs_reauth("expired")
    assert await s.account.check_session() == "needs_reauth"
    assert not argv_out.exists()


async def test_base_argv_uses_session_dir(tmp_path: Path) -> None:
    s = build_account_stack(tmp_path)
    argv = s.account.base_argv()
    assert argv[argv.index("--cookie-directory") + 1] == str(s.paths.session)
    assert argv[argv.index("--username") + 1] == "me@example.com"


async def test_update_new_apple_id_resets_state(tmp_path: Path) -> None:
    s = build_account_stack(tmp_path)
    s.store.set_library("shared", "SharedSync-X")
    s.account.mark_ok()
    s.account.update(apple_id="Other@Example.com", password="new")
    loaded = s.store.load()
    assert loaded is not None
    assert loaded.apple_id == "other@example.com"
    assert s.store.password() == "new"
    assert s.account.state().state == "unknown"
    assert s.store.library("shared") is None


async def test_snapshot_never_contains_password(tmp_path: Path) -> None:
    s = build_account_stack(tmp_path)
    snap = s.account.snapshot()
    assert snap["apple_id"] == "me@example.com"
    assert snap["has_password"] is True
    assert "pw" not in json.dumps(snap)


async def test_stale_reauthenticating_state_is_reset_on_startup(tmp_path: Path) -> None:
    s = build_account_stack(tmp_path)
    s.account.mark_ok()
    verified = s.account.state().last_verified_at
    s.db.kv_set_json(
        "account_state",
        AccountState("reauthenticating", since=verified, last_verified_at=verified).to_json(),
    )
    again = AccountService(
        paths=s.paths,
        store=s.store,
        db=s.db,
        lock=s.lock,
        bus=s.bus,
        notifier=s.notifier,
        icloudpd_cmd=[],
        idle_timeout=lambda: 1.0,
    )
    st = again.state()
    assert st.state == "unknown"
    assert st.last_verified_at == verified
    assert st.reason is None


async def test_unexpected_error_still_finishes_the_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(self: ReauthAttempt) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(ReauthAttempt, "start", boom)
    s = build_account_stack(tmp_path)
    s.account.mark_needs_reauth("expired")
    attempt = await s.account.start_reauth()
    await s.account.wait_attempt()
    record = s.db.get_attempt(attempt.id)
    assert record is not None
    assert record.outcome == "failed"
    assert record.ended_at is not None
    assert s.account.state().state == "needs_reauth"
    second = await s.account.start_reauth()
    assert second is not attempt
    third = await s.account.restart_reauth()
    assert third is not second


async def test_cancel_while_waiting_for_the_lock_finishes_the_record(tmp_path: Path) -> None:
    s = build_account_stack(tmp_path)
    release = asyncio.Event()

    async def check() -> None:
        async with s.lock.hold(AccountLock.RUN, "check"):
            await release.wait()

    holder = asyncio.create_task(check())
    await asyncio.sleep(0)
    attempt = await s.account.start_reauth()
    await asyncio.sleep(0.05)
    await s.account.cancel_reauth()
    release.set()
    await holder
    record = s.db.get_attempt(attempt.id)
    assert record is not None
    assert record.outcome == "cancelled"
    assert record.ended_at is not None
    assert s.account.state().state != "reauthenticating"
    assert (await s.account.start_reauth()) is not attempt
    await s.account.cancel_reauth()
