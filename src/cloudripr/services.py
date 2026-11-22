"""Builds and holds every service. One instance per app."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import tzinfo

from fastapi import Request

from cloudripr.account.service import AccountService
from cloudripr.engine.hook import install_hook
from cloudripr.engine.lock import AccountLock
from cloudripr.events import EventBus
from cloudripr.library.index import LibraryIndex
from cloudripr.library.thumbs import Thumbs
from cloudripr.migration import migrate
from cloudripr.notify.email import Notifier, Sender, apprise_send
from cloudripr.paths import DataPaths
from cloudripr.runs.gate import DryRunGate
from cloudripr.runs.service import RunService
from cloudripr.scheduler.service import Scheduler
from cloudripr.store.account_store import AccountStore
from cloudripr.store.db import StateDB
from cloudripr.store.policy_store import PolicyStore
from cloudripr.store.secrets import SecretStore
from cloudripr.store.settings import ServerSettings, SettingsStore


SMTP_SECRET = "_smtp"  # policy names must start alphanumeric, so this can't collide


@dataclass
class SettingsBox:
    current: ServerSettings


@dataclass
class Services:
    paths: DataPaths
    db: StateDB
    bus: EventBus
    lock: AccountLock
    policies: PolicyStore
    secrets: SecretStore
    settings_store: SettingsStore
    settings: SettingsBox
    account_store: AccountStore
    notifier: Notifier
    account: AccountService
    library: LibraryIndex
    thumbs: Thumbs
    gate: DryRunGate
    runs: RunService
    scheduler: Scheduler
    icloudpd_version: str


def build_services(
    paths: DataPaths,
    *,
    icloudpd_cmd: list[str],
    icloudpd_version: str,
    sender: Sender = apprise_send,
    local_tz: tzinfo | None = None,
    poll_interval: float = 1.0,
) -> Services:
    paths.ensure()
    install_hook(paths.hook_script)
    db = StateDB(paths.state_db)
    db.mark_unfinished_runs_failed("The server restarted while this run was in progress.")
    db.mark_unfinished_attempts("interrupted")
    bus = EventBus()
    lock = AccountLock()
    policies = PolicyStore(paths.policies)
    policies.load()
    secrets = SecretStore(paths.secrets)
    settings_store = SettingsStore(paths.settings_file)
    account_store = AccountStore(paths.account)
    gate = DryRunGate(db)
    migrate(
        paths=paths,
        policies=policies,
        secrets=secrets,
        account_store=account_store,
        settings_store=settings_store,
        gate=gate,
        db=db,
    )
    box = SettingsBox(settings_store.load())
    notifier = Notifier(
        settings=lambda: box.current.email,
        smtp_password=lambda: secrets.get(SMTP_SECRET),
        db=db,
        sender=sender,
    )
    account = AccountService(
        paths=paths,
        store=account_store,
        db=db,
        lock=lock,
        bus=bus,
        notifier=notifier,
        icloudpd_cmd=icloudpd_cmd,
        idle_timeout=lambda: box.current.idle_timeout_minutes * 60.0,
        poll_interval=poll_interval,
    )
    library = LibraryIndex(paths.library_db)
    thumbs = Thumbs(library, paths.cache)
    runs = RunService(
        paths=paths,
        policies=policies,
        account=account,
        account_store=account_store,
        db=db,
        lock=lock,
        gate=gate,
        library=library,
        thumbs=thumbs,
        notifier=notifier,
        bus=bus,
        settings=lambda: box.current,
        icloudpd_version=icloudpd_version,
        poll_interval=poll_interval,
    )

    async def catch_up() -> None:
        await runs.catch_up()

    account.on_reauth_success = catch_up
    scheduler = Scheduler(
        policies=policies,
        runs=runs,
        account=account,
        notifier=notifier,
        settings=lambda: box.current,
        local_tz=local_tz,
    )
    return Services(
        paths=paths,
        db=db,
        bus=bus,
        lock=lock,
        policies=policies,
        secrets=secrets,
        settings_store=settings_store,
        settings=box,
        account_store=account_store,
        notifier=notifier,
        account=account,
        library=library,
        thumbs=thumbs,
        gate=gate,
        runs=runs,
        scheduler=scheduler,
        icloudpd_version=icloudpd_version,
    )


def get_services(request: Request) -> Services:
    return request.app.state.services
