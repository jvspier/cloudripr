from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloudripr.store.db import RunRecord
from tests.api.conftest import configure_account
from tests.helpers import wait_until


def setup_policy(client: TestClient, target: Path, *, primed: bool) -> None:
    configure_account(client)
    target.mkdir(exist_ok=True)
    client.put("/api/policies/p", json={"name": "p", "directory": str(target), "cron": "0 3 * * *"})
    if primed:
        svc = client.app.state.services  # type: ignore[attr-defined]
        svc.gate.clear("p")  # an established policy: creation armed the gate
        svc.db.save_run(
            RunRecord(
                id="p-old",
                policy="p",
                trigger="schedule",
                status="success",
                started_at=datetime(2026, 1, 1, tzinfo=UTC),
                icloudpd_version="1.32.3",
            )
        )
        (target / ".folderstructure").write_text("{:%Y/%m/%d}")


def latest(client: TestClient) -> dict:
    return client.get("/api/runs", params={"policy": "p", "limit": 1}).json()[0]


def test_run_details_log_and_items(client: TestClient, tmp_path: Path) -> None:
    setup_policy(client, tmp_path / "photos", primed=True)
    run_id = client.post("/api/policies/p/run").json()["id"]
    wait_until(lambda: client.get(f"/api/runs/{run_id}").json()["status"] == "success")
    data = client.get(f"/api/runs/{run_id}").json()
    assert data["downloaded"] == 2
    assert data["file_count"] == 2
    log = client.get(f"/api/runs/{run_id}/log")
    assert log.status_code == 200
    assert "Downloaded" in log.text
    files = client.get(f"/api/runs/{run_id}/items").json()["files"]
    assert len(files) == 2
    assert files[0].endswith(".HEIC")
    assert client.get("/api/runs/nope").status_code == 404
    assert client.post(f"/api/runs/{run_id}/stop").status_code == 404


def test_stop_active_run(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "silent")
    monkeypatch.setenv("ICLOUDPD_SIM_SECONDS", "20")
    setup_policy(client, tmp_path / "photos", primed=True)
    run_id = client.post("/api/policies/p/run").json()["id"]
    wait_until(lambda: client.get(f"/api/runs/{run_id}").json()["status"] == "running")
    assert client.post(f"/api/runs/{run_id}/stop").json() == {"ok": True}
    wait_until(lambda: client.get(f"/api/runs/{run_id}").json()["status"] == "stopped")


def test_gate_review_and_approve(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_COUNT", "150")
    setup_policy(client, tmp_path / "photos", primed=False)
    blocked_id = client.post("/api/policies/p/run").json()["id"]
    wait_until(
        lambda: client.get(f"/api/runs/{blocked_id}").json()["status"] == "gate_blocked", timeout=15
    )
    review = client.get(f"/api/runs/{blocked_id}").json()["gate_review"]
    assert review["count"] == 150
    assert len(review["sample"]) == 150
    approved = client.post(f"/api/runs/{blocked_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["trigger"] == "gate"
    wait_until(lambda: latest(client)["status"] == "success", timeout=20)
    assert client.post(f"/api/runs/{blocked_id}/approve").status_code == 409


def test_log_path_cannot_escape(client: TestClient) -> None:
    svc = client.app.state.services  # type: ignore[attr-defined]
    svc.db.save_run(
        RunRecord(
            id="evil",
            policy="p",
            trigger="manual",
            status="failed",
            started_at=datetime.now(UTC),
            log_path="/etc/passwd",
        )
    )
    assert client.get("/api/runs/evil/log").status_code == 404
