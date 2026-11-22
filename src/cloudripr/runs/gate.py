"""Dry-run gate: protect the existing library from mass re-downloads."""

from __future__ import annotations

from typing import Literal, cast

from cloudripr.store.db import StateDB


GateState = Literal["armed", "blocked", "approved"]


class DryRunGate:
    """State per policy in kv `gate:<policy>`:

    armed    → next run is a dry run (migration, naming settings changed)
    blocked  → the last dry run found too much; stays a dry run until approved
    approved → next run is real (set after a passing dry run or by the user)
    (absent) → dry run only if there's no real success yet, or icloudpd changed
    """

    def __init__(self, db: StateDB) -> None:
        self._db = db

    def _key(self, policy: str) -> str:
        return f"gate:{policy}"

    def state(self, policy: str) -> GateState | None:
        return cast(GateState | None, self._db.kv_get(self._key(policy)))

    def arm(self, policy: str) -> None:
        self._db.kv_set(self._key(policy), "armed")

    def block(self, policy: str) -> None:
        self._db.kv_set(self._key(policy), "blocked")

    def approve(self, policy: str) -> None:
        self._db.kv_set(self._key(policy), "approved")

    def clear(self, policy: str) -> None:
        self._db.kv_delete(self._key(policy))

    def needs_dry_run(self, policy: str, icloudpd_version: str) -> bool:
        state = self.state(policy)
        if state == "approved":
            return False
        if state in ("armed", "blocked"):
            return True
        last = self._db.last_success(policy)
        return last is None or last.icloudpd_version != icloudpd_version

    @staticmethod
    def passes(would_download: int, threshold: int) -> bool:
        return would_download <= threshold
