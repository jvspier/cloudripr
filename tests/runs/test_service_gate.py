from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from cloudripr.runs import service as service_mod
from cloudripr.store.models import Filters
from tests.helpers import build_run_stack, eventually, wait_final


@pytest.fixture(autouse=True)
def sim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "ok")


async def _second_run(stack, first_id: str):  # noqa: ANN001, ANN202
    await eventually(lambda: len(stack.a.db.list_runs(policy="p")) >= 2, timeout=15)
    newest = stack.a.db.list_runs(policy="p")[0]
    assert newest.id != first_id
    return await wait_final(stack, newest.id)


async def test_first_run_is_a_dry_run_then_real(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_COUNT", "3")
    s = build_run_stack(tmp_path, primed=False)
    s.gate.arm("p")  # migrated: checked even though the folder looks empty
    dry = await wait_final(s, (await s.runs.trigger("p", "schedule")).id)
    assert dry.status == "success"
    assert dry.dry_run is True
    assert dry.would_download == 3
    assert dry.downloaded == 0
    assert s.a.db.run_files(dry.id) == []  # nothing written
    real = await _second_run(s, dry.id)
    assert real.trigger == "gate"
    assert real.dry_run is False
    assert real.downloaded == 3
    assert s.gate.state("p") is None
    assert (s.root / ".folderstructure").exists()


async def test_existing_files_are_not_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_COUNT", "3")
    s = build_run_stack(tmp_path, primed=False)
    for i in (1, 2):
        p = s.root / f"2026/10/IMG_000{i}.HEIC"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\0" * 64)
    dry = await wait_final(s, (await s.runs.trigger("p", "schedule")).id)
    assert dry.would_download == 1
    assert (s.root / ".folderstructure").exists()  # existing layout adopted
    real = await _second_run(s, dry.id)
    assert real.downloaded == 1


async def test_gate_blocks_mass_download_until_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_COUNT", "150")
    s = build_run_stack(tmp_path, primed=False)
    s.gate.arm("p")
    blocked = await wait_final(s, (await s.runs.trigger("p", "schedule")).id)
    assert blocked.status == "gate_blocked"
    assert blocked.would_download == 150
    assert s.gate.state("p") == "blocked"
    sample = json.loads(s.a.db.kv_get("gate_sample:p") or "{}")
    assert sample["count"] == 150
    assert len(sample["sample"]) == 150
    await eventually(lambda: "Check needed before downloading: p" in s.a.sender.titles)
    assert len(s.a.db.list_runs(policy="p")) == 1  # nothing else started
    approved = await s.runs.approve_gate("p")
    real = await wait_final(s, approved.id)
    assert real.status == "success"
    assert real.downloaded == 150
    assert real.dry_run is False


async def test_policy_threshold_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_COUNT", "3")
    s = build_run_stack(tmp_path, primed=False, gate_threshold=2)
    s.gate.arm("p")
    blocked = await wait_final(s, (await s.runs.trigger("p", "schedule")).id)
    assert blocked.status == "gate_blocked"


async def test_icloudpd_upgrade_arms_the_gate(tmp_path: Path) -> None:
    s = build_run_stack(tmp_path, version="1.32.4")  # primed with 1.32.3
    dry = await wait_final(s, (await s.runs.trigger("p", "schedule")).id)
    assert dry.dry_run is True
    real = await _second_run(s, dry.id)  # don't leave the follow-up run dangling
    assert real.status == "success"
    assert real.icloudpd_version == "1.32.4"


async def test_filters_remove_unwanted_new_files(tmp_path: Path) -> None:
    s = build_run_stack(tmp_path, filters=Filters(file_suffixes=[".jpg"]))
    final = await wait_final(s, (await s.runs.trigger("p", "manual")).id)
    assert final.status == "success"
    assert final.filter_deleted == 2
    assert final.filter_kept == 0
    assert list(s.root.rglob("*.HEIC")) == []
    assert s.a.db.run_files(final.id) == []


async def test_shared_library_lookup_is_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv_out = tmp_path / "argv.jsonl"
    monkeypatch.setenv("ICLOUDPD_SIM_ARGV_OUT", str(argv_out))
    monkeypatch.setenv("ICLOUDPD_SIM_SHARED_LIB", "SharedSync-ABC")
    s = build_run_stack(tmp_path, library_kind="shared")
    await wait_final(s, (await s.runs.trigger("p", "manual")).id)
    await wait_final(s, (await s.runs.trigger("p", "manual")).id)
    calls = [json.loads(line) for line in argv_out.read_text().splitlines()]
    assert sum("--list-libraries" in c for c in calls) == 1
    downloads = [c for c in calls if "--list-libraries" not in c]
    assert all(c[c.index("--library") + 1] == "SharedSync-ABC" for c in downloads)
    assert s.a.store.library("shared") == "SharedSync-ABC"


async def test_catch_up_runs_skipped_policies(tmp_path: Path) -> None:
    s = build_run_stack(tmp_path)
    s.a.account.mark_needs_reauth("expired")
    skipped = await s.runs.trigger("p", "schedule")
    assert skipped.status == "skipped"
    s.a.account.mark_ok()
    started = await s.runs.catch_up()
    assert [r.trigger for r in started] == ["catch-up"]
    assert (await wait_final(s, started[0].id)).status == "success"
    assert await s.runs.catch_up() == []  # last run is now a success


async def test_filters_never_touch_files_that_were_not_downloaded_this_run(
    tmp_path: Path,
) -> None:
    """Empty index baseline (disk was unmounted), then the old library appears."""
    s = build_run_stack(tmp_path, filters=Filters(file_suffixes=[".jpg"]))
    s.library.scan(s.root)
    assert s.library.has_root(s.root)
    assert s.library.count(s.root) == 0
    old = []
    for i in range(1, 5):
        p = s.root / f"2019/05/OLD_000{i}.HEIC"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\0" * 64)
        old.append(p)
    final = await wait_final(s, (await s.runs.trigger("p", "manual")).id)
    assert final.status == "success"
    assert all(p.exists() for p in old)
    assert final.filter_deleted == 2
    assert s.a.db.run_files(final.id) == []


async def test_approved_gate_with_policy_dry_run_does_not_loop(tmp_path: Path) -> None:
    s = build_run_stack(tmp_path, icloudpd={"dry_run": True})
    s.gate.approve("p")
    rec = await s.runs.trigger("p", "manual")
    await wait_final(s, rec.id)
    await asyncio.sleep(0.5)
    assert len(s.a.db.list_runs(policy="p")) == 2  # the primed "p-old" plus this one
    assert s.runs.active_for("p") is None


async def test_empty_folder_of_a_new_policy_skips_the_safety_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_COUNT", "3")
    s = build_run_stack(tmp_path, primed=False)
    run = await wait_final(s, (await s.runs.trigger("p", "schedule")).id)
    assert run.status == "success"
    assert run.dry_run is False
    assert run.downloaded == 3
    assert len(s.a.db.list_runs(policy="p")) == 1
    assert "nothing can be downloaded twice" in Path(run.log_path or "").read_text()


async def test_dry_run_stops_early_once_over_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service_mod, "GATE_CAP_MIN", 5)
    monkeypatch.setenv("ICLOUDPD_SIM_COUNT", "200")
    monkeypatch.setenv("ICLOUDPD_SIM_SLEEP", "0.02")
    s = build_run_stack(tmp_path, primed=False, gate_threshold=0)
    s.gate.arm("p")
    blocked = await wait_final(s, (await s.runs.trigger("p", "schedule")).id)
    assert blocked.status == "gate_blocked"
    assert 5 < blocked.would_download < 200
    assert "at least" in (blocked.reason or "")
    sample = json.loads(s.a.db.kv_get("gate_sample:p") or "{}")
    assert sample["partial"] is True
    assert sample["count"] == blocked.would_download
    assert s.gate.state("p") == "blocked"


async def test_dry_run_counter_updates_while_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_COUNT", "40")
    monkeypatch.setenv("ICLOUDPD_SIM_SLEEP", "0.05")
    s = build_run_stack(tmp_path, primed=False)
    s.gate.arm("p")
    rec = await s.runs.trigger("p", "schedule")

    def counting() -> bool:
        active = s.runs.active_for("p")
        return active is not None and active.dry_run and (active.would_download or 0) >= 3

    await eventually(counting, timeout=10)
    await s.runs.stop(rec.id)
    await wait_final(s, rec.id)


async def test_icloudpd_upgrade_checks_only_recent_photos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv_out = tmp_path / "argv.jsonl"
    monkeypatch.setenv("ICLOUDPD_SIM_ARGV_OUT", str(argv_out))
    s = build_run_stack(tmp_path, version="1.32.4")  # primed with 1.32.3
    dry = await wait_final(s, (await s.runs.trigger("p", "schedule")).id)
    assert dry.dry_run is True
    await _second_run(s, dry.id)
    dry_argv, real_argv = (json.loads(line) for line in argv_out.read_text().splitlines())
    assert "--dry-run" in dry_argv
    assert dry_argv[dry_argv.index("--recent") + 1] == str(service_mod.GATE_CAP_MIN)
    assert "--recent" not in real_argv


async def test_migration_check_covers_the_whole_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv_out = tmp_path / "argv.jsonl"
    monkeypatch.setenv("ICLOUDPD_SIM_ARGV_OUT", str(argv_out))
    s = build_run_stack(tmp_path, primed=False)
    s.gate.arm("p")
    dry = await wait_final(s, (await s.runs.trigger("p", "schedule")).id)
    assert dry.dry_run is True
    assert "--recent" not in json.loads(argv_out.read_text().splitlines()[0])
    await _second_run(s, dry.id)
