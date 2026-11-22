"""The single iCloud account: state, re-authentication, session check."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal

from cloudripr.account.reauth import AttemptError, ReauthAttempt
from cloudripr.engine.argv import base_args
from cloudripr.engine.lock import AccountLock
from cloudripr.engine.logwriter import LogWriter
from cloudripr.engine.noninteractive import NonInteractiveRun
from cloudripr.events import EventBus
from cloudripr.notify.email import Notifier
from cloudripr.paths import DataPaths
from cloudripr.store.account_store import Account, AccountStore
from cloudripr.store.db import AuthAttemptRecord, StateDB


log = logging.getLogger(__name__)

STATE_KEY = "account_state"
BAD_PASSWORD_REASON = (
    "Apple rejected the stored Apple ID password. Update it under Settings → Account."
)
StateName = Literal["unknown", "ok", "needs_reauth", "reauthenticating"]


class AccountNotConfigured(Exception):  # noqa: N818
    def __init__(self) -> None:
        super().__init__("Add your Apple ID and password under Settings → Account first.")


class RunInProgress(Exception):  # noqa: N818
    def __init__(self, policy: str) -> None:
        super().__init__(
            f"A backup run ({policy}) is in progress. Stop it or wait for it to finish."
        )
        self.policy = policy


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass
class AccountState:
    state: StateName = "unknown"
    since: datetime | None = None
    last_verified_at: datetime | None = None
    reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "since": self.since.isoformat() if self.since else None,
            "last_verified_at": self.last_verified_at.isoformat()
            if self.last_verified_at
            else None,
            "reason": self.reason,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> AccountState:
        return cls(
            state=data["state"],
            since=_dt(data.get("since")),
            last_verified_at=_dt(data.get("last_verified_at")),
            reason=data.get("reason"),
        )


class AccountService:
    def __init__(
        self,
        *,
        paths: DataPaths,
        store: AccountStore,
        db: StateDB,
        lock: AccountLock,
        bus: EventBus,
        notifier: Notifier,
        icloudpd_cmd: list[str],
        idle_timeout: Callable[[], float],
        reauth_timeout: float = 600.0,
        poll_interval: float = 1.0,
    ) -> None:
        self._paths = paths
        self._store = store
        self._db = db
        self._lock = lock
        self._bus = bus
        self._notifier = notifier
        self._cmd = icloudpd_cmd
        self._idle_timeout = idle_timeout
        self._reauth_timeout = reauth_timeout
        self._poll = poll_interval
        self.on_reauth_success: Callable[[], Awaitable[None]] | None = None
        self._attempt: ReauthAttempt | None = None
        self._attempt_task: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        # Attempts live only in memory, so a persisted "reauthenticating" is stale.
        stale = self.state()
        if stale.state == "reauthenticating":
            self._db.kv_set_json(
                STATE_KEY,
                AccountState("unknown", last_verified_at=stale.last_verified_at).to_json(),
            )

    # ---- state ------------------------------------------------------------

    def state(self) -> AccountState:
        raw = self._db.kv_get_json(STATE_KEY)
        return AccountState.from_json(raw) if raw else AccountState()

    def _save_state(self, st: AccountState) -> None:
        self._db.kv_set_json(STATE_KEY, st.to_json())
        self._bus.publish("account", self.snapshot())

    def snapshot(self) -> dict[str, Any]:
        account = self._store.load()
        return {
            "apple_id": account.apple_id if account else None,
            "domain": account.domain if account else "com",
            "has_password": self._store.password() is not None,
            **self.state().to_json(),
            "attempt": self._attempt.snapshot() if self._attempt else None,
            "busy_with": self._lock.holder,
        }

    def configured(self) -> bool:
        return self._store.load() is not None and self._store.password() is not None

    def base_argv(self) -> list[str]:
        account = self._store.load()
        if account is None:
            raise AccountNotConfigured()
        return [*self._cmd, *base_args(account, self._paths.session)]

    def password(self) -> str:
        value = self._store.password()
        if value is None:
            raise AccountNotConfigured()
        return value

    def update(
        self,
        *,
        apple_id: str | None = None,
        domain: Literal["com", "cn"] | None = None,
        password: str | None = None,
    ) -> None:
        current = self._store.load()
        if apple_id is not None or domain is not None:
            new = Account(
                apple_id=apple_id
                if apple_id is not None
                else (current.apple_id if current else ""),
                domain=domain or (current.domain if current else "com"),
            )
            if new != current:
                self._store.save(new)
                if current is None or new.apple_id != current.apple_id:
                    self._store.clear_library("shared")
                    self._db.kv_set_json(STATE_KEY, AccountState().to_json())
        if password is not None:
            self._store.set_password(password)
        self._bus.publish("account", self.snapshot())

    def mark_ok(self) -> None:
        st = self.state()
        now = datetime.now(UTC)
        since = st.since if st.state == "ok" and st.since else now
        self._save_state(AccountState("ok", since=since, last_verified_at=now))
        self._notifier.clear_reauth()

    def mark_needs_reauth(self, reason: str) -> None:
        st = self.state()
        if st.state == "needs_reauth":
            return
        self._save_state(
            AccountState(
                "needs_reauth",
                since=datetime.now(UTC),
                last_verified_at=st.last_verified_at,
                reason=reason,
            )
        )
        self._spawn(self._notifier.reauth_needed(reason))

    # ---- re-authentication -------------------------------------------------

    def current_attempt(self) -> ReauthAttempt | None:
        return self._attempt

    async def start_reauth(self) -> ReauthAttempt:
        if not self.configured():
            raise AccountNotConfigured()
        if self._attempt is not None and not self._attempt.finished:
            return self._attempt
        holder = self._lock.holder
        if holder is not None and holder.startswith("run:"):
            raise RunInProgress(holder.removeprefix("run:"))
        attempt_id = f"auth-{datetime.now(UTC):%Y%m%dT%H%M%S}-{secrets.token_hex(2)}"
        attempt = ReauthAttempt(
            attempt_id=attempt_id,
            argv=[*self.base_argv(), "--auth-only"],
            password=self.password(),
            log=LogWriter(self._paths.auth_logs / f"{attempt_id}.log"),
            timeout=self._reauth_timeout,
            on_change=self._on_attempt_change,
        )
        self._attempt = attempt
        self._db.save_attempt(
            AuthAttemptRecord(
                id=attempt.id, started_at=attempt.started_at, log_path=str(attempt.log_path)
            )
        )
        self._attempt_task = asyncio.create_task(self._drive(attempt))
        self._bus.publish("reauth", attempt.snapshot())
        return attempt

    async def _drive(self, attempt: ReauthAttempt) -> None:
        before: AccountState | None = None
        try:
            async with self._lock.hold(AccountLock.REAUTH, "reauth"):
                before = self.state()
                if not attempt.finished:
                    self._save_state(replace(before, state="reauthenticating"))
                try:
                    await attempt.start()
                    outcome = await attempt.wait()
                except Exception:
                    log.exception("re-authentication attempt failed unexpectedly")
                    await attempt.abort("Internal error during sign-in; start over.")
                    outcome = await attempt.wait()
        except asyncio.CancelledError:
            await attempt.cancel()
            await attempt.wait()
            self._record_attempt(attempt, "cancelled")
            self._restore_if_reauthenticating(before)
            self._bus.publish("reauth", attempt.snapshot())
            raise
        self._record_attempt(attempt, outcome)
        if outcome == "succeeded":
            self.mark_ok()
            if self.on_reauth_success is not None:
                try:
                    await self.on_reauth_success()
                except Exception:
                    log.exception("catch-up after re-authentication failed")
        else:
            self._restore_if_reauthenticating(before)
        self._bus.publish("reauth", attempt.snapshot())

    def _record_attempt(self, attempt: ReauthAttempt, outcome: str) -> None:
        self._db.save_attempt(
            AuthAttemptRecord(
                id=attempt.id,
                started_at=attempt.started_at,
                ended_at=attempt.ended_at,
                outcome=outcome,
                log_path=str(attempt.log_path),
            )
        )

    def _restore_if_reauthenticating(self, before: AccountState | None) -> None:
        if before is not None and self.state().state == "reauthenticating":
            self._save_state(before)

    def _on_attempt_change(self, attempt: ReauthAttempt) -> None:
        self._bus.publish("reauth", attempt.snapshot())

    def _require_attempt(self) -> ReauthAttempt:
        if self._attempt is None or self._attempt.finished:
            raise AttemptError("Not waiting for a code right now. Start over to get a new code.")
        return self._attempt

    async def submit_code(self, code: str) -> None:
        await self._require_attempt().submit_code(code)

    async def request_sms(self, index: str) -> None:
        await self._require_attempt().request_sms(index)

    async def wait_attempt(self) -> None:
        if self._attempt_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._attempt_task

    async def cancel_reauth(self) -> None:
        attempt, task = self._attempt, self._attempt_task
        if attempt is not None and not attempt.finished:
            await attempt.cancel()
        if task is not None and not task.done() and self._lock.holder != "reauth":
            task.cancel()  # still waiting for the lock
        await self.wait_attempt()

    async def restart_reauth(self) -> ReauthAttempt:
        await self.cancel_reauth()
        return await self.start_reauth()

    # ---- session check ----------------------------------------------------

    async def check_session(self) -> str:
        if not self.configured():
            return "not_configured"
        if self.state().state == "needs_reauth":
            return "needs_reauth"  # already known; don't sign in for nothing
        log_path = self._paths.auth_logs / "session-check.log"
        log_path.unlink(missing_ok=True)
        async with self._lock.hold(AccountLock.RUN, "check"):
            writer = LogWriter(log_path)
            result = await NonInteractiveRun(
                [*self.base_argv(), "--auth-only"],
                password=self.password(),
                log=writer,
                hook_script=self._paths.hook_script,
                marker_dir=self._paths.hook_markers,
                idle_timeout=self._idle_timeout(),
                poll_interval=self._poll,
            ).run()
            writer.close()
        if result.twofa_required:
            self.mark_needs_reauth("Apple asked for a new sign-in (found by the evening check).")
            return "needs_reauth"
        if result.bad_password:
            self.mark_needs_reauth(BAD_PASSWORD_REASON)
            return "needs_reauth"
        if result.exit_code == 0:
            self.mark_ok()
            return "ok"
        return "error"

    # ---- lifecycle --------------------------------------------------------

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def shutdown(self) -> None:
        await self.cancel_reauth()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
