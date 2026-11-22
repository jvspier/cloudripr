from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from cloudripr.scheduler.service import Scheduler
from cloudripr.store.models import Policy
from cloudripr.store.settings import ServerSettings


AMS = ZoneInfo("Europe/Amsterdam")


def policy(
    name: str = "p",
    *,
    cron: str = "0 3 * * *",
    tz: str | None = "Europe/Amsterdam",
    enabled: bool = True,
) -> Policy:
    return Policy(
        name=name, username="u@x.com", directory="/d", cron=cron, timezone=tz, enabled=enabled
    )


class FakePolicies:
    def __init__(self, *items: Policy) -> None:
        self.items = list(items)

    def all(self) -> list[Policy]:
        return self.items


class FakeRuns:
    def __init__(self, fail: bool = False) -> None:
        self.triggered: list[tuple[str, str]] = []
        self.fail = fail

    async def trigger(self, policy_name: str, trigger: str) -> object:
        if self.fail:
            raise RuntimeError("boom")
        self.triggered.append((policy_name, trigger))
        return None


class FakeAccount:
    def __init__(self) -> None:
        self.state_name = "ok"
        self.checks = 0

    def state(self) -> SimpleNamespace:
        return SimpleNamespace(state=self.state_name)

    async def check_session(self) -> str:
        self.checks += 1
        return "ok"


class FakeNotifier:
    def __init__(self) -> None:
        self.reminders: list[datetime] = []

    async def remind_if_due(self, now: datetime) -> bool:
        self.reminders.append(now)
        return False


def make(
    *items: Policy, settings: ServerSettings | None = None, runs: FakeRuns | None = None
) -> tuple[Scheduler, FakeRuns, FakeAccount, FakeNotifier]:
    r, a, n = runs or FakeRuns(), FakeAccount(), FakeNotifier()
    s = Scheduler(
        policies=FakePolicies(*items),
        runs=r,
        account=a,
        notifier=n,
        settings=lambda: settings or ServerSettings(),
        local_tz=AMS,
    )
    return s, r, a, n


def test_fires_at_local_time_once_per_minute() -> None:
    s, *_ = make(policy())
    # 14 Oct 2026 is CEST (UTC+2): 03:00 local = 01:00 UTC.
    assert s.due(datetime(2026, 10, 14, 1, 0, 20, tzinfo=UTC)) == [("run", "p")]
    assert s.due(datetime(2026, 10, 14, 1, 0, 50, tzinfo=UTC)) == []
    assert s.due(datetime(2026, 10, 14, 1, 1, 0, tzinfo=UTC)) == []
    assert s.due(datetime(2026, 10, 15, 1, 0, 0, tzinfo=UTC)) == [("run", "p")]


def test_disabled_policy_never_fires() -> None:
    s, *_ = make(policy(enabled=False))
    assert s.due(datetime(2026, 10, 14, 1, 0, tzinfo=UTC)) == []


def test_policy_without_timezone_uses_local_zone() -> None:
    s, *_ = make(policy(tz=None))
    assert s.due(datetime(2026, 10, 14, 1, 0, tzinfo=UTC)) == [("run", "p")]


def test_next_run_at_is_in_policy_timezone() -> None:
    s, *_ = make(policy())
    nxt = s.next_run_at(policy(), after=datetime(2026, 10, 14, 12, 0, tzinfo=UTC))
    assert (nxt.year, nxt.month, nxt.day, nxt.hour, nxt.minute) == (2026, 10, 15, 3, 0)
    assert nxt.utcoffset() == timedelta(hours=2)


def test_session_check_once_per_day() -> None:
    s, *_ = make()
    at_19 = datetime(2026, 10, 14, 17, 0, 10, tzinfo=UTC)  # 19:00 in Amsterdam
    assert s.due(at_19) == [("check", "")]
    assert s.due(at_19 + timedelta(seconds=30)) == []
    assert s.due(at_19 + timedelta(days=1)) == [("check", "")]


def test_session_check_can_be_disabled() -> None:
    s, *_ = make(settings=ServerSettings(session_check_time=""))
    assert s.due(datetime(2026, 10, 14, 17, 0, tzinfo=UTC)) == []


def test_reminder_only_while_needing_reauth() -> None:
    s, _, account, _ = make()
    now = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
    assert s.due(now) == []
    account.state_name = "needs_reauth"
    assert s.due(now) == [("remind", "")]


async def test_apply_dispatches_actions() -> None:
    s, runs, account, notifier = make()
    now = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
    await s.apply([("run", "p"), ("check", ""), ("remind", "")], now)
    assert runs.triggered == [("p", "schedule")]
    assert notifier.reminders == [now]
    for _ in range(50):
        if account.checks:
            break
        await asyncio.sleep(0.01)
    assert account.checks == 1


async def test_apply_survives_failures() -> None:
    s, _, _, notifier = make(runs=FakeRuns(fail=True))
    now = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
    await s.apply([("run", "p"), ("remind", "")], now)
    assert notifier.reminders == [now]


async def test_run_forever_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Scheduler, "TICK_SECONDS", 0.01)
    s, *_ = make()
    task = asyncio.create_task(s.run_forever())
    await asyncio.sleep(0.05)
    s.stop()
    await asyncio.wait_for(task, timeout=1)


def test_bad_policy_is_skipped_but_others_fire() -> None:
    bad = Policy.model_construct(
        name="bad",
        username="u@x.com",
        directory="/d",
        cron="0 3 * * *",
        timezone="Not/AZone",
        enabled=True,
    )
    bad_cron = Policy.model_construct(
        name="badcron",
        username="u@x.com",
        directory="/d",
        cron="nonsense",
        timezone="Europe/Amsterdam",
        enabled=True,
    )
    s, *_ = make(bad, bad_cron, policy("good"))
    assert s.due(datetime(2026, 10, 14, 1, 0, tzinfo=UTC)) == [("run", "good")]


def test_failing_account_state_does_not_drop_runs() -> None:
    s, _, account, _ = make(policy())

    def boom() -> SimpleNamespace:
        raise RuntimeError("boom")

    account.state = boom  # type: ignore[method-assign]
    assert s.due(datetime(2026, 10, 14, 1, 0, tzinfo=UTC)) == [("run", "p")]


async def test_run_forever_survives_due_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Scheduler, "TICK_SECONDS", 0.01)
    s, *_ = make()
    calls: list[int] = []

    def flaky(now: datetime) -> list:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return []

    monkeypatch.setattr(s, "due", flaky)
    task = asyncio.create_task(s.run_forever())
    await asyncio.sleep(0.1)
    s.stop()
    await asyncio.wait_for(task, timeout=1)
    assert len(calls) >= 2
