"""Download runs: queueing, execution, outcomes and records."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import secrets
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cloudripr.account.service import BAD_PASSWORD_REASON, AccountService
from cloudripr.engine.argv import download_args
from cloudripr.engine.lock import AccountLock
from cloudripr.engine.logwriter import LogWriter
from cloudripr.engine.noninteractive import NonInteractiveResult, NonInteractiveRun
from cloudripr.engine.output import OutputEvent
from cloudripr.events import EventBus
from cloudripr.library.index import LibraryIndex
from cloudripr.library.thumbs import Thumbs
from cloudripr.notify.email import Notifier
from cloudripr.paths import DataPaths
from cloudripr.runs.filters import evaluate_all
from cloudripr.runs.folder_structure import (
    SENTINEL_NAME,
    check_or_raise,
    effective_pattern,
    remember,
)
from cloudripr.runs.gate import DryRunGate
from cloudripr.runs.libraries import parse_library_names
from cloudripr.store.account_store import AccountStore
from cloudripr.store.db import FINAL_STATUSES, RunRecord, StateDB
from cloudripr.store.models import Policy
from cloudripr.store.policy_store import PolicyStore
from cloudripr.store.settings import ServerSettings


log = logging.getLogger(__name__)

REAUTH_REASON = "Apple needs you to sign in again (re-authenticate)."
GATE_SAMPLE_KEY = "gate_sample:{policy}"
ICLOUD_TOTAL_KEY = "icloud_total:{policy}"
# A safety-check dry run stops once this many files (or 10x the limit) would be
# downloaded: enough to tell a naming mismatch, which reaches back into old
# folders, from a busy few weeks. After an icloudpd upgrade only this many of
# the newest photos are checked: a naming change shows there already.
GATE_CAP_MIN = 1000
_LIBRARY_ERROR = re.compile(r"librar", re.IGNORECASE)

Outcome = tuple[str, str | None]  # (status, reason)


def _now() -> datetime:
    return datetime.now(UTC)


def _this_runs_files(root: Path, added: list[str], downloaded: list[str]) -> list[Path]:
    def resolve(p: Path) -> Path:
        return (p if p.is_absolute() else root / p).resolve()

    got = [resolve(Path(d)) for d in downloaded]
    got_set = set(got)
    result: list[Path] = []
    for rel in added:
        path = resolve(root / rel)
        companion = any(
            g.parent == path.parent and (path.stem == g.stem or path.stem.startswith(g.stem + "_"))
            for g in got
        )
        if path in got_set or companion:
            result.append(root / rel)
    return result


@dataclass
class _Active:
    record: RunRecord
    task: asyncio.Task[None] | None = None
    executor: NonInteractiveRun | None = None
    stop_requested: bool = False
    gate_dry: bool = False
    gate_cut: bool = False  # the safety check stopped early, over the cap


class RunService:
    def __init__(
        self,
        *,
        paths: DataPaths,
        policies: PolicyStore,
        account: AccountService,
        account_store: AccountStore,
        db: StateDB,
        lock: AccountLock,
        gate: DryRunGate,
        library: LibraryIndex,
        thumbs: Thumbs,
        notifier: Notifier,
        bus: EventBus,
        settings: Callable[[], ServerSettings],
        icloudpd_version: str,
        poll_interval: float = 1.0,
    ) -> None:
        self._paths = paths
        self._policies = policies
        self._account = account
        self._account_store = account_store
        self._db = db
        self._lock = lock
        self._gate = gate
        self._library = library
        self._thumbs = thumbs
        self._notifier = notifier
        self._bus = bus
        self._settings = settings
        self._version = icloudpd_version
        self._poll = poll_interval
        self._active: dict[str, _Active] = {}
        self._tasks: set[asyncio.Task[Any]] = set()
        self._last_progress: dict[str, float] = {}

    # ---- queries ----------------------------------------------------------

    def active_for(self, policy: str) -> RunRecord | None:
        for active in self._active.values():
            if active.record.policy == policy:
                return active.record
        return None

    def in_flight(self) -> list[RunRecord]:
        return [a.record for a in self._active.values()]

    # ---- commands ---------------------------------------------------------

    async def trigger(self, policy_name: str, trigger: str) -> RunRecord:
        existing = self.active_for(policy_name)
        if existing is not None:
            return existing
        rec = RunRecord(
            id=f"{policy_name}-{_now():%Y%m%dT%H%M%S}-{secrets.token_hex(2)}",
            policy=policy_name,
            trigger=trigger,
            status="queued",
            started_at=_now(),
            icloudpd_version=self._version,
        )
        problem = self._precheck(policy_name)
        if problem is not None:
            self._finish(rec, *problem)
            return rec
        self._save(rec)
        active = _Active(rec)
        self._active[rec.id] = active
        active.task = asyncio.create_task(self._execute(active))
        return rec

    async def stop(self, run_id: str) -> bool:
        active = self._active.get(run_id)
        if active is None:
            return False
        active.stop_requested = True
        if active.executor is not None:
            await active.executor.stop()
        elif active.record.status == "queued" and active.task is not None:
            active.task.cancel()
        return True

    async def approve_gate(self, policy: str) -> RunRecord:
        self._gate.approve(policy)
        return await self.trigger(policy, "gate")

    async def catch_up(self) -> list[RunRecord]:
        started: list[RunRecord] = []
        for policy in self._policies.all():
            if not policy.enabled:
                continue
            last = self._db.last_run(policy.name)
            if last is not None and last.status in ("skipped", "needs_reauth"):
                started.append(await self.trigger(policy.name, "catch-up"))
        return started

    async def shutdown(self) -> None:
        for active in list(self._active.values()):
            await self.stop(active.record.id)
        pending = [a.task for a in self._active.values() if a.task is not None]
        pending += list(self._tasks)
        if pending:
            await asyncio.wait(pending, timeout=15)

    # ---- checks -----------------------------------------------------------

    def _precheck(self, name: str) -> Outcome | None:
        policy = self._policies.get(name)
        if policy is None:
            return ("failed", f"Policy {name!r} no longer exists.")
        if not self._account.configured():
            return ("failed", "Add your Apple ID and password under Settings → Account first.")
        if self._account.state().state == "needs_reauth":
            return ("skipped", REAUTH_REASON)
        root = Path(policy.directory)
        seen_key = f"library_seen:{name}"
        if (root / SENTINEL_NAME).exists():
            self._db.kv_set(seen_key, "1")
        known = (
            self._db.kv_get(seen_key) is not None
            or self._library.count(root) > 0
            or self._db.last_success(name) is not None
        )
        if known and not (root / SENTINEL_NAME).exists():
            return (
                "failed",
                f"The photo folder {root} looks empty or isn't mounted (its {SENTINEL_NAME} "
                "marker is missing). Nothing was downloaded, so nothing can be downloaded "
                "twice. Check the mount, then run again. If the photos really are there, "
                f"restore the marker: create {root / SENTINEL_NAME} containing "
                f"{effective_pattern(policy.icloudpd.get('folder_structure'))}",
            )
        try:
            check_or_raise(root, policy.icloudpd.get("folder_structure"))
        except RuntimeError as exc:
            return ("failed", str(exc))
        return None

    # ---- execution --------------------------------------------------------

    async def _execute(self, active: _Active) -> None:
        rec = active.record
        try:
            async with self._lock.hold(AccountLock.RUN, f"run:{rec.policy}"):
                if active.stop_requested:
                    self._finish(rec, "stopped", "Stopped before it started.")
                    return
                problem = self._precheck(rec.policy)
                if problem is not None:
                    self._finish(rec, *problem)
                    return
                rec.status = "running"
                rec.started_at = _now()
                self._save(rec)
                await self._run_policy(active)
        except asyncio.CancelledError:
            if rec.status not in FINAL_STATUSES:
                self._finish(rec, "stopped", "Stopped before it started.")
        except Exception as exc:
            log.exception("run %s crashed", rec.id)
            if rec.status not in FINAL_STATUSES:
                self._finish(rec, "failed", f"Internal error: {exc}")
        finally:
            self._active.pop(rec.id, None)
            self._last_progress.pop(rec.id, None)
        if (
            rec.status == "success"
            and active.gate_dry
            and self._gate.state(rec.policy) == "approved"
        ):
            await self.trigger(rec.policy, "gate")

    async def _run_policy(self, active: _Active) -> None:
        rec = active.record
        policy = self._policies.get(rec.policy)
        assert policy is not None  # _precheck ran under the lock
        log_path = self._paths.runs / rec.policy / f"{rec.id}.log"
        rec.log_path = str(log_path)
        writer = LogWriter(log_path)
        try:
            status, reason = await self._run_steps(active, policy, writer)
        finally:
            writer.close()
        if writer.errors:
            note = (
                f"The run log could not be written ({writer.errors} errors); check free disk space."
            )
            reason = f"{reason} {note}" if reason else note
        self._finish(rec, status, reason)

    async def _run_steps(self, active: _Active, policy: Policy, writer: LogWriter) -> Outcome:  # noqa: C901
        rec = active.record
        library, problem = await self._resolve_library(active, policy, writer)
        if problem is not None:
            return problem
        root = Path(policy.directory)
        if not self._library.has_root(root):
            writer.write("INFO     Indexing the existing library before the first run…")
            first = await asyncio.to_thread(self._library.scan, root)
            if first.total > 0:
                remember(root, policy.icloudpd.get("folder_structure"))  # adopt existing layout
        own_dry_run = bool(policy.icloudpd.get("dry_run"))
        gate_dry = not own_dry_run and self._gate.needs_dry_run(policy.name, self._version)
        if gate_dry and self._nothing_to_protect(policy.name, root):
            gate_dry = False
            writer.write(
                "INFO     Safety check skipped: the photo folder is empty, "
                "so nothing can be downloaded twice."
            )
        rec.dry_run = gate_dry or own_dry_run
        active.gate_dry = gate_dry
        self._save(rec)
        cap = self._gate_cap(policy)
        would: list[str] = []
        downloaded: list[str] = []

        recent = None
        if gate_dry and self._gate.state(policy.name) is None:
            if self._db.last_success(policy.name) is not None:
                recent = cap  # only icloudpd changed: the newest photos tell
        # With --recent, icloudpd's "Downloading N …" is the limit, not the library size.
        full_library = recent is None and not policy.icloudpd.get("recent")

        def on_event(event: OutputEvent) -> None:
            if event.kind == "total" and event.value and full_library:
                self._db.kv_set_json(
                    ICLOUD_TOTAL_KEY.format(policy=policy.name),
                    {"count": int(event.value), "seen_at": _now().isoformat()},
                )
            if event.kind == "would_download" and event.value:
                would.append(event.value)
            elif event.kind == "downloaded":
                if event.value:
                    downloaded.append(event.value)
                if not rec.dry_run:
                    rec.downloaded += 1
                    self._progress(rec)
            if rec.dry_run and event.kind in ("would_download", "downloaded"):
                rec.would_download = max(len(would), len(downloaded))
                self._progress(rec)
                if gate_dry and rec.would_download > cap and not active.gate_cut:
                    active.gate_cut = True
                    writer.write(
                        f"INFO     Safety check: more than {cap} new files, so it stopped early."
                    )
                    if active.executor is not None:
                        self._spawn(active.executor.stop())

        if gate_dry:
            writer.write("INFO     Safety check: this run is a dry run; nothing is written.")
        argv = [
            *self._account.base_argv(),
            *download_args(policy, library=library, dry_run=gate_dry, recent=recent),
        ]
        result = await self._run_icloudpd(active, argv, writer, on_event)
        rec.exit_code = result.exit_code
        cut_short = active.gate_cut and not active.stop_requested
        failure = None if cut_short else self._failure(result, policy)
        if failure is not None:
            return failure
        self._account.mark_ok()
        if gate_dry:
            # Don't fail open if icloudpd rewords its dry-run line: icloudpd also logs
            # "Downloaded <path>" in a dry run, so use whichever list is larger.
            listed = would if would and len(would) >= len(downloaded) else downloaded
            return self._judge_dry_run(rec, policy, listed, writer, partial=cut_short)
        if own_dry_run:
            rec.would_download = len(would)
            return (
                "success",
                f"Dry run (policy setting): {len(would)} file(s) would be downloaded.",
            )
        await self._after_download(rec, policy, writer, downloaded)
        self._gate.clear(policy.name)
        remember(root, policy.icloudpd.get("folder_structure"))
        return ("success", None)

    async def _run_icloudpd(
        self,
        active: _Active,
        argv: list[str],
        writer: LogWriter,
        on_event: Callable[[OutputEvent], None],
    ) -> NonInteractiveResult:
        executor = NonInteractiveRun(
            argv,
            password=self._account.password(),
            log=writer,
            hook_script=self._paths.hook_script,
            marker_dir=self._paths.hook_markers,
            idle_timeout=self._settings().idle_timeout_minutes * 60,
            on_event=on_event,
            poll_interval=self._poll,
        )
        active.executor = executor
        if active.stop_requested:
            await executor.stop()
        try:
            return await executor.run()
        finally:
            active.executor = None

    def _failure(self, result: NonInteractiveResult, policy: Policy) -> Outcome | None:
        if result.spawn_error is not None:
            return ("failed", f"Could not start icloudpd: {result.spawn_error}")
        if result.stopped:
            return ("stopped", "Stopped by you.")
        if result.twofa_required:
            self._account.mark_needs_reauth("Apple asked for a new sign-in during a backup run.")
            return ("needs_reauth", REAUTH_REASON)
        if result.bad_password:
            self._account.mark_needs_reauth(BAD_PASSWORD_REASON)
            return ("failed", BAD_PASSWORD_REASON)
        if result.idle_timeout:
            minutes = self._settings().idle_timeout_minutes
            return ("failed", f"No activity for {minutes} minutes, so the run was stopped.")
        if result.exit_code != 0:
            if (
                policy.library_kind == "shared"
                and result.last_error
                and _LIBRARY_ERROR.search(result.last_error)
            ):
                self._account_store.clear_library("shared")  # re-resolve next time
            return ("failed", result.last_error or f"icloudpd exited with code {result.exit_code}.")
        return None

    async def _resolve_library(
        self, active: _Active, policy: Policy, writer: LogWriter
    ) -> tuple[str | None, Outcome | None]:
        if policy.library_kind is None:
            return None, None  # download_args falls back to policy.icloudpd["library"]
        if policy.library_kind == "personal":
            return "PrimarySync", None
        cached = self._account_store.library("shared")
        if cached:
            return cached, None
        writer.write("INFO     Looking up the shared library…")
        names: list[str] = []

        def on_event(event: OutputEvent) -> None:
            if event.kind == "line":
                names.extend(parse_library_names(event.text))

        argv = [
            *self._account.base_argv(),
            "--directory",
            str(policy.directory),
            "--list-libraries",
        ]
        result = await self._run_icloudpd(active, argv, writer, on_event)
        failure = self._failure(result, policy)
        if failure is not None:
            return None, failure
        shared = [n for n in names if n != "PrimarySync"]
        if not shared:
            return None, (
                "failed",
                "No shared library found on this iCloud account. "
                "Switch the policy to the personal library.",
            )
        self._account_store.set_library("shared", shared[0])
        return shared[0], None

    def _threshold(self, policy: Policy) -> int:
        if policy.gate_threshold is not None:
            return policy.gate_threshold
        return self._settings().gate_threshold

    def _gate_cap(self, policy: Policy) -> int:
        return max(GATE_CAP_MIN, 10 * self._threshold(policy))

    def _nothing_to_protect(self, name: str, root: Path) -> bool:
        """A new policy whose folder is empty: there is no library to download twice.

        An armed gate (migration, import, naming change) still checks: there, an
        empty folder more likely means the library isn't mounted.
        """
        return (
            self._gate.state(name) is None
            and self._db.last_success(name) is None
            and self._library.count(root) == 0
        )

    def _judge_dry_run(
        self,
        rec: RunRecord,
        policy: Policy,
        would: list[str],
        writer: LogWriter,
        *,
        partial: bool = False,
    ) -> Outcome:
        rec.would_download = len(would)
        threshold = self._threshold(policy)
        if not partial and DryRunGate.passes(len(would), threshold):
            self._gate.approve(policy.name)
            writer.write(
                f"INFO     Safety check passed: {len(would)} new file(s) (limit {threshold}). "
                "Starting the real run."
            )
            return ("success", f"Safety check passed: {len(would)} new file(s).")
        self._gate.block(policy.name)
        self._db.kv_set_json(
            GATE_SAMPLE_KEY.format(policy=policy.name),
            {"run_id": rec.id, "count": len(would), "partial": partial, "sample": would[:200]},
        )
        self._spawn(self._notifier.gate_blocked(policy.name, rec.id, len(would), partial=partial))
        amount = f"at least {len(would)}" if partial else str(len(would))
        return (
            "gate_blocked",
            f"Safety check: {amount} files would be downloaded (limit {threshold}). "
            "Review them before downloading.",
        )

    async def _after_download(
        self, rec: RunRecord, policy: Policy, writer: LogWriter, downloaded: list[str]
    ) -> None:
        root = Path(policy.directory)
        scan = await asyncio.to_thread(self._library.scan, root)
        # Only what icloudpd reported as downloaded in THIS run may be filtered or
        # recorded. "added" alone can be the whole library after an empty baseline.
        new_files = _this_runs_files(root, scan.added, downloaded)
        if new_files and not policy.filters.is_empty():
            decisions = await asyncio.to_thread(evaluate_all, new_files, policy.filters)
            for decision in decisions:
                if decision.kept:
                    rec.filter_kept += 1
                    writer.write(f"INFO     Filter: kept {decision.path} ({decision.reason})")
                    continue
                try:
                    await asyncio.to_thread(os.unlink, decision.path)
                    rec.filter_deleted += 1
                    writer.write(f"INFO     Filter: deleted {decision.path} ({decision.reason})")
                except OSError as exc:
                    writer.write(f"WARNING  Filter: could not delete {decision.path}: {exc}")
            writer.write(
                f"INFO     Filter summary: kept {rec.filter_kept}, deleted {rec.filter_deleted}"
            )
            if rec.filter_deleted:
                await asyncio.to_thread(self._library.scan, root)
        kept = [str(p) for p in new_files if p.exists()]
        self._db.add_run_files(rec.id, kept)
        if kept:
            self._spawn(self._check_new_files(rec, kept))

    async def _check_new_files(self, rec: RunRecord, paths: list[str]) -> None:
        """Thumbnail this run's new files in the background; count the unreadable ones."""
        try:
            items = self._library.items_for_paths(paths)
            rec.unreadable = await asyncio.to_thread(self._thumbs.check, items)
            self._save(rec)
        except Exception:
            log.exception("checking the new files of run %s failed", rec.id)

    # ---- bookkeeping ------------------------------------------------------

    def _finish(self, rec: RunRecord, status: str, reason: str | None) -> None:
        rec.status = status
        rec.reason = reason
        rec.ended_at = _now()
        self._save(rec)
        for old in self._db.prune_runs(rec.policy, keep=self._settings().retention_runs):
            if old.log_path:
                with contextlib.suppress(OSError):
                    Path(old.log_path).unlink(missing_ok=True)
        if status == "failed":
            self._spawn(self._notifier.run_failed(rec.policy, rec.id, reason or "Unknown error."))
        elif status == "success" and not rec.dry_run:
            self._spawn(self._notifier.run_succeeded(rec.policy, rec.id, rec.downloaded))

    def _save(self, rec: RunRecord) -> None:
        self._db.save_run(rec)
        self._bus.publish("run", rec.to_json())

    def _progress(self, rec: RunRecord) -> None:
        now = asyncio.get_running_loop().time()
        if now - self._last_progress.get(rec.id, 0.0) >= 1.0:
            self._last_progress[rec.id] = now
            self._bus.publish("run", rec.to_json())

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
