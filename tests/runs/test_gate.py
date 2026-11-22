from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from cloudripr.runs.gate import DryRunGate
from cloudripr.store.db import RunRecord, StateDB


def success(db: StateDB, version: str) -> None:
    db.save_run(
        RunRecord(
            id="r1",
            policy="p",
            trigger="schedule",
            status="success",
            started_at=datetime(2026, 10, 1, tzinfo=UTC),
            icloudpd_version=version,
        )
    )


def test_no_success_yet_needs_dry_run(tmp_path: Path) -> None:
    gate = DryRunGate(StateDB(tmp_path / "s.db"))
    assert gate.state("p") is None
    assert gate.needs_dry_run("p", "1.32.3") is True


def test_same_version_success_needs_no_dry_run(tmp_path: Path) -> None:
    db = StateDB(tmp_path / "s.db")
    success(db, "1.32.3")
    gate = DryRunGate(db)
    assert gate.needs_dry_run("p", "1.32.3") is False
    assert gate.needs_dry_run("p", "1.32.4") is True  # icloudpd upgraded


def test_explicit_states(tmp_path: Path) -> None:
    db = StateDB(tmp_path / "s.db")
    success(db, "1.32.3")
    gate = DryRunGate(db)
    gate.arm("p")
    assert gate.state("p") == "armed"
    assert gate.needs_dry_run("p", "1.32.3") is True
    gate.block("p")
    assert gate.needs_dry_run("p", "1.32.3") is True
    gate.approve("p")
    assert gate.needs_dry_run("p", "9.9.9") is False  # approval wins over version check
    gate.clear("p")
    assert gate.state("p") is None


def test_threshold() -> None:
    assert DryRunGate.passes(100, 100) is True
    assert DryRunGate.passes(101, 100) is False
    assert DryRunGate.passes(0, 0) is True
