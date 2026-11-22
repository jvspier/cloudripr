"""Cron scheduling, the evening session check and re-auth reminders."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import zoneinfo
from collections.abc import Callable, Coroutine
from datetime import UTC, date, datetime, tzinfo
from typing import Any, Literal, Protocol

from croniter import croniter

from cloudripr.store.models import Policy
from cloudripr.store.settings import ServerSettings


log = logging.getLogger(__name__)

Action = tuple[Literal["run", "check", "remind"], str]


class _Policies(Protocol):
    def all(self) -> list[Policy]: ...  # pragma: no cover


class _Runs(Protocol):
    async def trigger(self, policy_name: str, trigger: str) -> object: ...  # pragma: no cover


class _Account(Protocol):
    def state(self) -> Any: ...  # noqa: ANN401  # pragma: no cover

    async def check_session(self) -> str: ...  # pragma: no cover


class _Notifier(Protocol):
    async def remind_if_due(self, now: datetime) -> bool: ...  # pragma: no cover


class Scheduler:
    TICK_SECONDS = 5.0

    def __init__(
        self,
        *,
        policies: _Policies,
        runs: _Runs,
        account: _Account,
        notifier: _Notifier,
        settings: Callable[[], ServerSettings],
        local_tz: tzinfo | None = None,
    ) -> None:
        self._policies = policies
        self._runs = runs
        self._account = account
        self._notifier = notifier
        self._settings = settings
        self._local_tz_override = local_tz
        self._fired: dict[str, datetime] = {}
        self._last_check: date | None = None
        self._stop = asyncio.Event()
        self._tasks: set[asyncio.Task[Any]] = set()

    def _local_tz(self) -> tzinfo:
        return self._local_tz_override or datetime.now().astimezone().tzinfo or UTC

    def tz_for(self, policy: Policy) -> tzinfo:
        return zoneinfo.ZoneInfo(policy.timezone) if policy.timezone else self._local_tz()

    def next_run_at(self, policy: Policy, *, after: datetime) -> datetime:
        return croniter(policy.cron, after.astimezone(self.tz_for(policy))).get_next(datetime)

    def due(self, now: datetime) -> list[Action]:
        actions: list[Action] = []
        for policy in self._policies.all():
            try:
                if not policy.enabled:
                    continue
                minute = now.astimezone(self.tz_for(policy)).replace(second=0, microsecond=0)
                if not croniter.match(policy.cron, minute):
                    continue
                if self._fired.get(policy.name) == minute:
                    continue
                self._fired[policy.name] = minute
                actions.append(("run", policy.name))
            except Exception:
                log.exception("scheduler: skipping policy %s", policy.name)
        actions.extend(self._session_check_due(now))
        try:
            if self._account.state().state == "needs_reauth":
                actions.append(("remind", ""))
        except Exception:
            log.exception("scheduler: account state read failed")
        return actions

    def _session_check_due(self, now: datetime) -> list[Action]:
        try:
            check_at = self._settings().session_check_time
            if check_at:
                local = now.astimezone(self._local_tz())
                if local.strftime("%H:%M") == check_at and self._last_check != local.date():
                    self._last_check = local.date()
                    return [("check", "")]
        except Exception:
            log.exception("scheduler: session check evaluation failed")
        return []

    async def apply(self, actions: list[Action], now: datetime) -> None:
        for kind, name in actions:
            try:
                if kind == "run":
                    await self._runs.trigger(name, "schedule")
                elif kind == "check":
                    # May wait behind a running backup for the account lock;
                    # never block the scheduler tick on it.
                    self._spawn(self._account.check_session())
                else:
                    await self._notifier.remind_if_due(now)
            except Exception:
                log.exception("scheduler action %s %s failed", kind, name)

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                now = datetime.now(UTC)
                await self.apply(self.due(now), now)
            except Exception:
                log.exception("scheduler tick failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self.TICK_SECONDS)

    def stop(self) -> None:
        self._stop.set()

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
