"""Shared test helpers (extended in later tasks)."""

from __future__ import annotations

import asyncio
import sys
import time
from collections.abc import Callable
from pathlib import Path


SIM_PATH = Path(__file__).parent / "fixtures" / "icloudpd_sim.py"
SIM_CMD: list[str] = [sys.executable, str(SIM_PATH)]


async def eventually(
    predicate: Callable[[], bool], timeout: float = 5.0, interval: float = 0.02
) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(interval)


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0, interval: float = 0.02) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(interval)


from cloudripr.store.settings import EmailSettings  # noqa: E402


EMAIL = EmailSettings(to="me@example.com", smtp_user="bot@example.com", app_url="http://nas:5000")


class FakeSender:
    """Stands in for apprise_send; records what would have been emailed."""

    def __init__(self, ok: bool = True, delay: float = 0.0, error: Exception | None = None) -> None:
        self.ok = ok
        self.delay = delay
        self.error = error
        self.calls: list[tuple[list[str], str, str]] = []

    def __call__(self, urls: list[str], title: str, body: str) -> bool:
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        self.calls.append((urls, title, body))
        return self.ok

    @property
    def titles(self) -> list[str]:
        return [title for _, title, _ in self.calls]


from dataclasses import dataclass  # noqa: E402

from cloudripr.account.service import AccountService  # noqa: E402
from cloudripr.engine.hook import install_hook  # noqa: E402
from cloudripr.engine.lock import AccountLock  # noqa: E402
from cloudripr.events import EventBus  # noqa: E402
from cloudripr.notify.email import Notifier  # noqa: E402
from cloudripr.paths import DataPaths  # noqa: E402
from cloudripr.store.account_store import Account, AccountStore  # noqa: E402
from cloudripr.store.db import StateDB  # noqa: E402


@dataclass
class AccountStack:
    paths: DataPaths
    db: StateDB
    bus: EventBus
    lock: AccountLock
    store: AccountStore
    sender: FakeSender
    notifier: Notifier
    account: AccountService


def build_account_stack(tmp_path: Path, *, configured: bool = True) -> AccountStack:
    paths = DataPaths(tmp_path / "data", tmp_path / "cache")
    paths.ensure()
    install_hook(paths.hook_script)
    db = StateDB(paths.state_db)
    bus = EventBus()
    lock = AccountLock()
    store = AccountStore(paths.account)
    if configured:
        store.save(Account(apple_id="me@example.com"))
        store.set_password("pw")
    sender = FakeSender()
    notifier = Notifier(settings=lambda: EMAIL, smtp_password=lambda: "pw", db=db, sender=sender)
    account = AccountService(
        paths=paths,
        store=store,
        db=db,
        lock=lock,
        bus=bus,
        notifier=notifier,
        icloudpd_cmd=SIM_CMD,
        idle_timeout=lambda: 30.0,
        reauth_timeout=10.0,
        poll_interval=0.05,
    )
    return AccountStack(paths, db, bus, lock, store, sender, notifier, account)


from datetime import UTC, datetime  # noqa: E402

from cloudripr.library.index import LibraryIndex  # noqa: E402
from cloudripr.library.thumbs import Thumbs  # noqa: E402
from cloudripr.runs.gate import DryRunGate  # noqa: E402
from cloudripr.runs.service import RunService  # noqa: E402
from cloudripr.store.db import FINAL_STATUSES, RunRecord  # noqa: E402
from cloudripr.store.models import Policy  # noqa: E402
from cloudripr.store.policy_store import PolicyStore  # noqa: E402
from cloudripr.store.settings import ServerSettings  # noqa: E402


VERSION = "1.32.3"


@dataclass
class Holder:
    value: ServerSettings


@dataclass
class RunStack:
    a: AccountStack
    policies: PolicyStore
    gate: DryRunGate
    library: LibraryIndex
    settings: Holder
    runs: RunService
    root: Path


def build_run_stack(
    tmp_path: Path,
    *,
    configured: bool = True,
    primed: bool = True,
    version: str = VERSION,
    **policy_kw: object,
) -> RunStack:
    """A configured account plus policy "p" downloading into tmp_path/photos.

    primed=True records a previous real success with the same icloudpd version and
    writes the folder-structure marker, so the dry-run gate stays closed.
    """
    a = build_account_stack(tmp_path, configured=configured)
    policies = PolicyStore(a.paths.policies)
    policies.load()
    gate = DryRunGate(a.db)
    library = LibraryIndex(a.paths.library_db)
    settings = Holder(ServerSettings())
    runs = RunService(
        paths=a.paths,
        policies=policies,
        account=a.account,
        account_store=a.store,
        db=a.db,
        lock=a.lock,
        gate=gate,
        library=library,
        thumbs=Thumbs(library, a.paths.cache),
        notifier=a.notifier,
        bus=a.bus,
        settings=lambda: settings.value,
        icloudpd_version=version,
        poll_interval=0.05,
    )

    async def _catch_up() -> None:
        await runs.catch_up()

    a.account.on_reauth_success = _catch_up
    root = tmp_path / "photos"
    root.mkdir()
    policies.put(
        Policy(name="p", username="me@example.com", directory=root, cron="0 3 * * *", **policy_kw)
    )  # type: ignore[arg-type]
    if primed:
        a.db.save_run(
            RunRecord(
                id="p-old",
                policy="p",
                trigger="schedule",
                status="success",
                started_at=datetime(2026, 1, 1, tzinfo=UTC),
                icloudpd_version=VERSION,
            )
        )
        (root / ".folderstructure").write_text("{:%Y/%m/%d}")
    return RunStack(a, policies, gate, library, settings, runs, root)


async def wait_final(stack: RunStack, run_id: str, timeout: float = 15.0) -> RunRecord:
    def done() -> bool:
        rec = stack.a.db.get_run(run_id)
        return rec is not None and rec.status in FINAL_STATUSES

    await eventually(done, timeout=timeout)
    rec = stack.a.db.get_run(run_id)
    assert rec is not None
    return rec
