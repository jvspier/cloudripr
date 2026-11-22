from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cloudripr.store.db import RunRecord
from cloudripr.store.models import Policy
from cloudripr.store.settings import ServerSettings
from tests.helpers import build_run_stack, eventually, wait_final


@pytest.fixture(autouse=True)
def sim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "ok")


async def test_successful_run_records_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_COUNT", "3")
    s = build_run_stack(tmp_path)
    events = s.a.bus.subscribe()
    rec = await s.runs.trigger("p", "manual")
    assert rec.status == "queued"
    final = await wait_final(s, rec.id)
    assert final.status == "success"
    assert final.downloaded == 3
    assert final.dry_run is False
    files = s.a.db.run_files(rec.id)
    assert files == [str(s.root / f"2026/10/IMG_000{i}.HEIC") for i in (1, 2, 3)]
    assert "Downloaded" in Path(final.log_path or "").read_text()
    assert s.a.account.state().state == "ok"
    assert s.gate.state("p") is None
    statuses = []
    while not events.empty():
        ev = events.get_nowait()
        if ev["type"] == "run":
            statuses.append(ev["data"]["status"])
    assert statuses[0] == "queued"
    assert "running" in statuses
    assert statuses[-1] == "success"


async def test_failure_is_recorded_and_emailed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "fail")
    s = build_run_stack(tmp_path)
    final = await wait_final(s, (await s.runs.trigger("p", "manual")).id)
    assert final.status == "failed"
    assert final.reason == "something went wrong"
    await eventually(lambda: "Backup failed: p" in s.a.sender.titles)


async def test_twofa_during_run_pauses_account_without_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    s = build_run_stack(tmp_path)
    final = await wait_final(s, (await s.runs.trigger("p", "schedule")).id)
    assert final.status == "needs_reauth"
    assert s.a.account.state().state == "needs_reauth"
    assert "Please enter" not in Path(final.log_path or "").read_text()
    await eventually(lambda: "iCloud needs you to sign in again" in s.a.sender.titles)


async def test_skipped_while_account_needs_reauth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv_out = tmp_path / "argv.jsonl"
    monkeypatch.setenv("ICLOUDPD_SIM_ARGV_OUT", str(argv_out))
    s = build_run_stack(tmp_path)
    s.a.account.mark_needs_reauth("expired")
    rec = await s.runs.trigger("p", "schedule")
    assert rec.status == "skipped"
    assert "re-authenticate" in (rec.reason or "")
    assert not argv_out.exists()


async def test_not_configured(tmp_path: Path) -> None:
    s = build_run_stack(tmp_path, configured=False)
    rec = await s.runs.trigger("p", "manual")
    assert rec.status == "failed"
    assert "Settings → Account" in (rec.reason or "")


async def test_refuses_when_library_folder_looks_unmounted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unmounted library disk shows up as an empty /downloads."""
    argv_out = tmp_path / "argv.jsonl"
    monkeypatch.setenv("ICLOUDPD_SIM_ARGV_OUT", str(argv_out))
    s = build_run_stack(tmp_path)  # primed: a real success exists
    (s.root / ".folderstructure").unlink()  # what an empty mount point looks like
    rec = await s.runs.trigger("p", "schedule")
    assert rec.status == "failed"
    assert "isn't mounted" in (rec.reason or "")
    assert f"create {s.root / '.folderstructure'} containing {{:%Y/%m/%d}}" in (rec.reason or "")
    assert not argv_out.exists()
    assert list(s.root.iterdir()) == []


async def test_unmount_guard_remembers_a_library_seen_before_any_success(
    tmp_path: Path,
) -> None:
    """Final review: no real success yet (switch-over night), then the mount disappears."""
    s = build_run_stack(tmp_path, primed=False)
    (s.root / ".folderstructure").write_text("{:%Y/%m/%d}")
    assert s.runs._precheck("p") is None  # first look at the library
    (s.root / ".folderstructure").unlink()
    outcome = s.runs._precheck("p")
    assert outcome is not None
    assert outcome[0] == "failed"
    assert "isn't mounted" in outcome[1]


async def test_folder_structure_mismatch(tmp_path: Path) -> None:
    s = build_run_stack(tmp_path, icloudpd={"folder_structure": "{:%Y}"})
    rec = await s.runs.trigger("p", "manual")
    assert rec.status == "failed"
    assert "Folder-structure mismatch" in (rec.reason or "")


async def test_stop_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "silent")
    monkeypatch.setenv("ICLOUDPD_SIM_SECONDS", "20")
    s = build_run_stack(tmp_path)
    rec = await s.runs.trigger("p", "manual")
    await eventually(lambda: s.a.db.get_run(rec.id).status == "running")  # type: ignore[union-attr]
    assert await s.runs.stop(rec.id) is True
    final = await wait_final(s, rec.id)
    assert final.status == "stopped"
    assert await s.runs.stop(rec.id) is False


async def test_runs_queue_behind_the_lock_and_dedupe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_COUNT", "4")
    monkeypatch.setenv("ICLOUDPD_SIM_SLEEP", "0.15")
    s = build_run_stack(tmp_path)
    q_root = tmp_path / "q-photos"
    q_root.mkdir()
    s.policies.put(Policy(name="q", username="me@example.com", directory=q_root, cron="0 3 * * *"))
    s.a.db.save_run(
        RunRecord(
            id="q-old",
            policy="q",
            trigger="schedule",
            status="success",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            icloudpd_version="1.32.3",
        )
    )
    (q_root / ".folderstructure").write_text("{:%Y/%m/%d}")
    p = await s.runs.trigger("p", "manual")
    q = await s.runs.trigger("q", "manual")
    assert (await s.runs.trigger("p", "manual")).id == p.id
    await eventually(lambda: s.a.lock.holder == "run:p")
    assert s.a.db.get_run(q.id).status == "queued"  # type: ignore[union-attr]
    assert (await wait_final(s, p.id)).status == "success"
    assert (await wait_final(s, q.id)).status == "success"


async def test_run_completes_when_log_unwritable(tmp_path: Path) -> None:
    """Review Focus #3: a broken log must not lose the run's outcome."""
    s = build_run_stack(tmp_path)
    (s.a.paths.runs / "p").write_text("a file where the log directory should be")
    final = await wait_final(s, (await s.runs.trigger("p", "manual")).id)
    assert final.status == "success"
    assert final.downloaded == 2
    assert "could not be written" in (final.reason or "")


async def test_retention(tmp_path: Path) -> None:
    s = build_run_stack(tmp_path)
    s.settings.value = ServerSettings(retention_runs=2)
    ids = []
    for _ in range(3):
        rec = await s.runs.trigger("p", "manual")
        await wait_final(s, rec.id)
        ids.append(rec.id)
    kept = [r.id for r in s.a.db.list_runs(policy="p")]
    assert kept == [ids[2], ids[1]]
    assert not (s.a.paths.runs / "p" / f"{ids[0]}.log").exists()


async def test_shutdown_stops_active_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "silent")
    monkeypatch.setenv("ICLOUDPD_SIM_SECONDS", "20")
    s = build_run_stack(tmp_path)
    rec = await s.runs.trigger("p", "manual")
    await eventually(lambda: s.a.db.get_run(rec.id).status == "running")  # type: ignore[union-attr]
    await asyncio.wait_for(s.runs.shutdown(), timeout=10)
    assert s.a.db.get_run(rec.id).status == "stopped"  # type: ignore[union-attr]
