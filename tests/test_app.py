from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from cloudripr.app import create_app, detect_icloudpd_version
from cloudripr.auth import Authenticator
from cloudripr.paths import DataPaths
from cloudripr.store.db import AuthAttemptRecord, RunRecord, StateDB
from tests.helpers import SIM_CMD, FakeSender


def build(paths: DataPaths, *, start_scheduler: bool = False):  # noqa: ANN201
    return create_app(
        paths=paths,
        authenticator=Authenticator(Authenticator.hash("long-enough")),
        session_secret="s" * 32,
        icloudpd_cmd=SIM_CMD,
        icloudpd_version="1.32.3",
        sender=FakeSender(),
        start_scheduler=start_scheduler,
    )


def test_detect_icloudpd_version() -> None:
    assert detect_icloudpd_version() == "1.34.0"


def test_startup_closes_interrupted_runs(tmp_path: Path) -> None:
    """Review Focus #2: nothing stays 'running' across a restart."""
    paths = DataPaths(tmp_path / "data", tmp_path / "cache")
    paths.ensure()
    db = StateDB(paths.state_db)
    db.save_run(
        RunRecord(
            id="r1",
            policy="p",
            trigger="schedule",
            status="running",
            started_at=datetime(2026, 10, 14, 1, tzinfo=UTC),
        )
    )
    db.save_attempt(AuthAttemptRecord(id="a1", started_at=datetime(2026, 10, 14, tzinfo=UTC)))
    db.close()
    app = build(paths)
    svc = app.state.services
    run = svc.db.get_run("r1")
    assert run is not None
    assert run.status == "failed"
    assert "restarted" in (run.reason or "")
    attempt = svc.db.get_attempt("a1")
    assert attempt is not None
    assert attempt.outcome == "interrupted"


def test_migration_runs_at_startup(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "data", tmp_path / "cache")
    paths.ensure()
    fixture = Path(__file__).parent / "fixtures" / "policies" / "icloud.toml"
    (paths.policies / "icloud.toml").write_text(fixture.read_text())
    (paths.secrets / "icloud.password").write_text("applepw")
    app = build(paths)
    assert app.state.services.account.configured() is True
    assert paths.hook_script.is_file()


def test_lifespan_starts_and_stops_scheduler(tmp_path: Path) -> None:
    app = build(DataPaths(tmp_path / "data", tmp_path / "cache"), start_scheduler=True)
    with TestClient(app) as c:
        assert c.get("/api/auth/status").status_code == 200
    # leaving the context ran shutdown without raising
