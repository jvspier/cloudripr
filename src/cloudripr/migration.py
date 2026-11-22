"""One-time migration from the previous app's /data layout. Idempotent."""

from __future__ import annotations

from datetime import UTC, datetime

from cloudripr.paths import DataPaths
from cloudripr.runs.gate import DryRunGate
from cloudripr.store.account_store import Account, AccountStore
from cloudripr.store.db import StateDB
from cloudripr.store.policy_store import PolicyStore
from cloudripr.store.secrets import SecretStore
from cloudripr.store.settings import SettingsStore


MIGRATED_KEY = "migrated_v2"
NOTES_KEY = "migration_notes"
# Policies that came with an existing library: naming is locked from the start,
# not only after their first real success in this app.
NAMING_FROZEN_KEY = "naming_frozen:{policy}"


def migrate(  # noqa: C901
    *,
    paths: DataPaths,
    policies: PolicyStore,
    secrets: SecretStore,
    account_store: AccountStore,
    settings_store: SettingsStore,
    gate: DryRunGate,
    db: StateDB,
) -> list[str]:
    if db.kv_get(MIGRATED_KEY):
        return []
    notes: list[str] = []
    all_policies = sorted(policies.all(), key=lambda p: p.name)

    if account_store.load() is None and all_policies:
        first = all_policies[0]
        account_store.save(
            Account(apple_id=first.username, domain=first.icloudpd.get("domain", "com"))
        )
        notes.append(f"Apple ID {first.username} is now the app's iCloud account.")
        password = secrets.get(first.name)
        if password and account_store.password() is None:
            account_store.set_password(password)
            notes.append("The Apple ID password moved to the account.")
        others = sorted({p.username.lower() for p in all_policies} - {first.username.lower()})
        if others:
            notes.append(
                f"Policies that used other Apple IDs ({', '.join(others)}) now use "
                f"{first.username}."
            )

    session_dir = str(paths.session)
    for policy in all_policies:
        if policy.icloudpd.get("cookie_directory") != session_dir:
            # Only for rollback: the previous app honours this key, so switching
            # back keeps using the same Apple session.
            policies.put(
                policy.model_copy(
                    update={"icloudpd": {**policy.icloudpd, "cookie_directory": session_dir}}
                )
            )
        gate.arm(policy.name)
        db.kv_set(NAMING_FROZEN_KEY.format(policy=policy.name), datetime.now(UTC).isoformat())
    if all_policies:
        notes.append(
            "The first run of each policy is a dry run, to confirm nothing gets downloaded twice."
        )
        if not any(paths.session.iterdir()):
            notes.append("No saved Apple session found; you may need to re-authenticate once.")

    settings = settings_store.load()
    legacy_urls = list(settings.apprise.get("urls") or [])
    if legacy_urls and not settings.email.extra_urls:
        settings.email.extra_urls = legacy_urls
        settings.email.on_success = bool(settings.apprise.get("on_success", False))
        settings.email.on_failure = bool(settings.apprise.get("on_failure", True))
        notes.append("Your existing Apprise notification URLs were kept.")
    if settings.retention_runs == 10:  # the old default
        settings.retention_runs = 30
    settings_store.save(settings)

    db.kv_set_json(NOTES_KEY, notes)
    db.kv_set(MIGRATED_KEY, datetime.now(UTC).isoformat())
    return notes
