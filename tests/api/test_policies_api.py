from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloudripr.migration import NAMING_FROZEN_KEY
from cloudripr.store.db import RunRecord
from tests.api.conftest import configure_account
from tests.helpers import wait_until


def body(name: str = "p", directory: Path | str = "/tmp/p", **extra: object) -> dict:
    return {
        "name": name,
        "directory": str(directory),
        "cron": "0 3 * * *",
        "timezone": "Europe/Amsterdam",
        "icloudpd": {"folder_structure": "{:%Y/%m}"},
        **extra,
    }


def prime_success(client: TestClient, name: str = "p") -> None:
    svc = client.app.state.services  # type: ignore[attr-defined]
    svc.db.save_run(
        RunRecord(
            id=f"{name}-old",
            policy=name,
            trigger="schedule",
            status="success",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            icloudpd_version="1.32.3",
        )
    )


def test_create_and_summary(client: TestClient) -> None:
    configure_account(client)
    r = client.put("/api/policies/p", json=body())
    assert r.status_code == 200
    data = r.json()
    svc = client.app.state.services  # type: ignore[attr-defined]
    assert data["username"] == "me@example.com"  # always the account's Apple ID
    assert data["icloudpd"]["cookie_directory"] == str(svc.paths.session)
    assert data["next_run_at"].endswith("+02:00") or data["next_run_at"].endswith("+01:00")
    assert "T03:00:00" in data["next_run_at"]
    assert data["last_run"] is None
    assert data["active_run"] is None
    assert data["naming_locked"] is False
    assert data["gate"] == "armed"
    assert [p["name"] for p in client.get("/api/policies").json()] == ["p"]


def test_validation_errors(client: TestClient) -> None:
    r = client.put("/api/policies/p", json=body(name="q"))
    assert r.status_code == 422
    assert r.json()["field"] == "name"
    r = client.put("/api/policies/p", json=body(cron="not cron"))
    assert r.status_code == 422
    assert r.json()["field"] == "cron"


def test_naming_lock(client: TestClient) -> None:
    configure_account(client)
    client.put("/api/policies/p", json=body())
    prime_success(client)
    assert client.get("/api/policies/p").json()["naming_locked"] is True
    # Non-naming changes are fine while locked.
    assert client.put("/api/policies/p", json=body(cron="0 4 * * *")).status_code == 200
    changed = body(cron="0 4 * * *", icloudpd={"folder_structure": "{:%Y}"})
    r = client.put("/api/policies/p", json=changed)
    assert r.status_code == 409
    assert r.json()["field"] == "naming"
    r = client.post("/api/policies/p/unlock", json={"confirm": "nope"})
    assert r.status_code == 422
    assert r.json()["field"] == "confirm"
    assert (
        client.post("/api/policies/p/unlock", json={"confirm": "p"}).json()["naming_locked"]
        is False
    )
    after = client.put("/api/policies/p", json=changed).json()
    assert after["gate"] == "armed"
    assert after["naming_locked"] is True


def test_secrets_are_never_returned(client: TestClient) -> None:
    configure_account(client)
    client.put("/api/policies/p", json=body(icloudpd={"smtp_password": "hunter2"}))
    assert "hunter2" not in client.get("/api/policies/p").text
    assert "hunter2" not in client.get("/api/policies/export").text
    # A save without the secret keeps the stored one.
    client.put("/api/policies/p", json=body(icloudpd={}))
    svc = client.app.state.services  # type: ignore[attr-defined]
    assert svc.policies.get("p").icloudpd["smtp_password"] == "hunter2"


def test_import_export_roundtrip(client: TestClient) -> None:
    configure_account(client)
    client.put("/api/policies/p", json=body())
    exported = client.get("/api/policies/export")
    assert exported.headers["content-type"].startswith("application/toml")
    client.delete("/api/policies/p")
    r = client.post("/api/policies/import", content=exported.content)
    assert r.json() == {"created": ["p"], "errors": []}
    again = client.post("/api/policies/import", content=exported.content).json()
    assert again["errors"] == [{"name": "p", "error": "already exists"}]
    bad = client.post("/api/policies/import", content=b"not = [toml")
    assert bad.status_code == 400


def test_delete(client: TestClient) -> None:
    client.put("/api/policies/p", json=body())
    assert client.delete("/api/policies/p").json() == {"ok": True}
    assert client.delete("/api/policies/p").status_code == 404
    assert client.get("/api/policies/p").status_code == 404


def test_run_now(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_COUNT", "2")
    configure_account(client)
    target = tmp_path / "photos"
    target.mkdir()
    client.put("/api/policies/p", json=body(directory=target))
    r = client.post("/api/policies/p/run")
    assert r.status_code == 202
    assert r.json()["status"] == "queued"
    # First run is the safety dry run; the real run follows automatically.
    wait_until(lambda: client.get("/api/policies/p").json()["last_success"] is not None, timeout=15)
    assert len(list(target.rglob("*.HEIC"))) == 2
    assert client.post("/api/policies/missing/run").status_code == 404


def test_recreate_cannot_bypass_naming_lock(client: TestClient) -> None:
    configure_account(client)
    client.put("/api/policies/p", json=body())
    prime_success(client)
    client.post("/api/policies/p/unlock", json={"confirm": "p"})
    client.delete("/api/policies/p")
    r = client.put("/api/policies/p", json=body(icloudpd={"size": "medium"}))
    assert r.status_code == 200
    assert r.json()["gate"] == "armed"
    assert r.json()["naming_locked"] is True


def test_import_arms_gate(client: TestClient) -> None:
    configure_account(client)
    client.put("/api/policies/p", json=body())
    exported = client.get("/api/policies/export")
    client.delete("/api/policies/p")
    assert client.post("/api/policies/import", content=exported.content).json()["created"] == ["p"]
    assert client.get("/api/policies/p").json()["gate"] == "armed"


def test_migrated_policy_is_locked_before_its_first_success(client: TestClient) -> None:
    configure_account(client)
    client.put("/api/policies/p", json=body())
    svc = client.app.state.services  # type: ignore[attr-defined]
    svc.db.kv_set(NAMING_FROZEN_KEY.format(policy="p"), "2026-11-22T00:00:00+00:00")
    assert client.get("/api/policies/p").json()["naming_locked"] is True
    changed = body(icloudpd={"folder_structure": "{:%Y}"})
    r = client.put("/api/policies/p", json=changed)
    assert r.status_code == 409
    assert r.json()["field"] == "naming"
    client.post("/api/policies/p/unlock", json={"confirm": "p"})
    after = client.put("/api/policies/p", json=changed).json()
    assert after["gate"] == "armed"
    assert after["naming_locked"] is True  # relocks after the deliberate change
