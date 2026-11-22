from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cloudripr.store.db import AuthAttemptRecord, RunRecord, StateDB


T0 = datetime(2026, 10, 14, 1, 0, tzinfo=UTC)


def _run(
    i: int,
    *,
    policy: str = "p",
    status: str = "success",
    dry: bool = False,
    version: str = "1.32.3",
) -> RunRecord:
    return RunRecord(
        id=f"{policy}-{i}",
        policy=policy,
        trigger="schedule",
        status=status,
        started_at=T0 + timedelta(minutes=i),
        dry_run=dry,
        icloudpd_version=version,
    )


@pytest.fixture
def db(tmp_path: Path) -> StateDB:
    return StateDB(tmp_path / "state.db")


def test_run_roundtrip_and_upsert(db: StateDB) -> None:
    rec = _run(1, status="running")
    db.save_run(rec)
    rec.status = "success"
    rec.ended_at = T0 + timedelta(minutes=5)
    rec.downloaded = 3
    rec.dry_run = True
    db.save_run(rec)
    got = db.get_run("p-1")
    assert got == rec
    assert got is not None
    assert got.dry_run is True
    assert got.ended_at == rec.ended_at


def test_to_json_serialises_datetimes(db: StateDB) -> None:
    data = _run(1).to_json()
    assert data["started_at"] == "2026-10-14T01:01:00+00:00"
    assert data["ended_at"] is None


def test_list_runs_newest_first_with_filter_and_limit(db: StateDB) -> None:
    for i in range(3):
        db.save_run(_run(i))
    db.save_run(_run(9, policy="q"))
    assert [r.id for r in db.list_runs(policy="p")] == ["p-2", "p-1", "p-0"]
    assert [r.id for r in db.list_runs(limit=2)] == ["q-9", "p-2"]
    last = db.last_run("p")
    assert last is not None
    assert last.id == "p-2"
    assert db.last_run("nope") is None


def test_last_success_ignores_dry_runs_and_failures(db: StateDB) -> None:
    db.save_run(_run(1))
    db.save_run(_run(2, dry=True))
    db.save_run(_run(3, status="failed"))
    last = db.last_success("p")
    assert last is not None
    assert last.id == "p-1"


def test_run_files(db: StateDB) -> None:
    db.save_run(_run(1))
    db.add_run_files("p-1", ["/d/b.HEIC", "/d/a.HEIC", "/d/a.HEIC"])
    assert db.run_files("p-1") == ["/d/a.HEIC", "/d/b.HEIC"]


def test_prune_keeps_newest_and_unfinished(db: StateDB) -> None:
    for i in range(5):
        db.save_run(_run(i))
    db.save_run(_run(0, status="running"))  # oldest, but unfinished
    db.add_run_files("p-1", ["/x"])
    removed = db.prune_runs("p", keep=2)
    assert sorted(r.id for r in removed) == ["p-1", "p-2"]
    assert [r.id for r in db.list_runs(policy="p")] == ["p-4", "p-3", "p-0"]
    assert db.run_files("p-1") == []


def test_prune_never_deletes_newest_real_success(db: StateDB) -> None:
    db.save_run(_run(0))  # the only real success
    db.save_run(_run(1, dry=True))
    for i in range(2, 8):
        db.save_run(_run(i, status="skipped"))
    removed = db.prune_runs("p", keep=2)
    assert "p-0" not in [r.id for r in removed]
    assert db.last_success("p") is not None
    assert [r.id for r in db.list_runs(policy="p")] == ["p-7", "p-6", "p-0"]


def test_mark_unfinished_runs_failed(db: StateDB) -> None:
    db.save_run(_run(1, status="queued"))
    db.save_run(_run(2, status="running"))
    db.save_run(_run(3, status="success"))
    assert db.mark_unfinished_runs_failed("server restarted") == 2
    r = db.get_run("p-2")
    assert r is not None
    assert r.status == "failed"
    assert r.reason == "server restarted"
    assert r.ended_at is not None
    ok = db.get_run("p-3")
    assert ok is not None
    assert ok.status == "success"


def test_attempts(db: StateDB) -> None:
    db.save_attempt(AuthAttemptRecord(id="a1", started_at=T0))
    db.save_attempt(
        AuthAttemptRecord(
            id="a2",
            started_at=T0 + timedelta(minutes=1),
            outcome="succeeded",
            ended_at=T0 + timedelta(minutes=2),
        )
    )
    assert [a.id for a in db.list_attempts()] == ["a2", "a1"]
    got = db.get_attempt("a2")
    assert got is not None
    assert got.outcome == "succeeded"
    assert got.to_json()["ended_at"] == "2026-10-14T01:02:00+00:00"


def test_mark_unfinished_attempts(db: StateDB) -> None:
    db.save_attempt(AuthAttemptRecord(id="a1", started_at=T0))
    assert db.mark_unfinished_attempts("interrupted") == 1
    got = db.get_attempt("a1")
    assert got is not None
    assert got.outcome == "interrupted"
    assert got.ended_at is not None


def test_kv(db: StateDB) -> None:
    assert db.kv_get("k") is None
    db.kv_set("k", "v1")
    db.kv_set("k", "v2")
    assert db.kv_get("k") == "v2"
    db.kv_set_json("j", {"a": [1, 2]})
    assert db.kv_get_json("j") == {"a": [1, 2]}
    assert db.kv_get_json("missing") is None
    db.kv_delete("k")
    assert db.kv_get("k") is None


def test_persists_across_reopen(tmp_path: Path) -> None:
    first = StateDB(tmp_path / "s.db")
    first.save_run(_run(1))
    first.close()
    second = StateDB(tmp_path / "s.db")
    assert second.get_run("p-1") is not None
