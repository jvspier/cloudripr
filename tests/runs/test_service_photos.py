from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cloudripr.store.db import StateDB
from tests.helpers import build_run_stack, eventually, wait_final


@pytest.fixture(autouse=True)
def sim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "ok")


async def test_real_run_records_unreadable_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_COUNT", "3")  # the sim writes 64 zero bytes: unreadable
    s = build_run_stack(tmp_path)
    run = await wait_final(s, (await s.runs.trigger("p", "manual")).id)
    assert run.status == "success"

    def checked() -> bool:
        rec = s.a.db.get_run(run.id)
        return rec is not None and rec.unreadable == 3

    await eventually(checked, timeout=10)


async def test_total_is_stored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_COUNT", "3")
    s = build_run_stack(tmp_path)
    await wait_final(s, (await s.runs.trigger("p", "manual")).id)
    total = s.a.db.kv_get_json("icloud_total:p")
    assert total is not None
    assert total["count"] == 3
    assert total["seen_at"]


def test_old_state_db_gains_unreadable_column(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (id TEXT PRIMARY KEY, policy TEXT NOT NULL, trigger TEXT NOT NULL,"
        " status TEXT NOT NULL, started_at TEXT NOT NULL, reason TEXT, ended_at TEXT,"
        " exit_code INTEGER, downloaded INTEGER NOT NULL DEFAULT 0,"
        " filter_kept INTEGER NOT NULL DEFAULT 0, filter_deleted INTEGER NOT NULL DEFAULT 0,"
        " dry_run INTEGER NOT NULL DEFAULT 0, would_download INTEGER, icloudpd_version TEXT,"
        " log_path TEXT)"
    )
    conn.execute(
        "INSERT INTO runs (id, policy, trigger, status, started_at) "
        "VALUES ('r1', 'p', 'manual', 'success', '2026-11-01T03:00:00+00:00')"
    )
    conn.commit()
    conn.close()
    state = StateDB(db)
    rec = state.get_run("r1")
    assert rec is not None
    assert rec.unreadable is None


async def test_recent_limited_run_does_not_store_a_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_COUNT", "3")
    s = build_run_stack(tmp_path, icloudpd={"recent": 3})
    await wait_final(s, (await s.runs.trigger("p", "manual")).id)
    assert s.a.db.kv_get_json("icloud_total:p") is None
