from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from cloudripr.store.db import AuthAttemptRecord
from tests.api.conftest import AppEnv, configure_account
from tests.helpers import wait_until


def attempt_state(c: TestClient) -> str | None:
    attempt = c.get("/api/account/reauth").json()["attempt"]
    return attempt["state"] if attempt else None


def test_requires_login(app_env: AppEnv) -> None:
    with TestClient(app_env.build()) as c:
        assert c.get("/api/account").status_code == 401


def test_initial_account(client: TestClient) -> None:
    data = client.get("/api/account").json()
    assert data["apple_id"] is None
    assert data["has_password"] is False
    assert data["state"] == "unknown"
    assert data["attempt"] is None
    assert data["versions"]["icloudpd"] == "1.32.3"
    assert data["migration_notes"] == []
    assert data["email_last_error"] is None
    assert data["has_session"] is False


def test_has_session_once_apple_session_files_exist(client: TestClient, app_env: AppEnv) -> None:
    (app_env.paths.session / "me").write_text("cookie")
    assert client.get("/api/account").json()["has_session"] is True


def test_update_account_normalises_and_hides_password(client: TestClient) -> None:
    r = client.put("/api/account", json={"apple_id": " Me@Example.com ", "password": "s3cret"})
    assert r.status_code == 200
    assert r.json()["apple_id"] == "me@example.com"
    assert r.json()["has_password"] is True
    assert "s3cret" not in r.text
    assert "s3cret" not in client.get("/api/account").text


def test_update_requires_apple_id_first(client: TestClient) -> None:
    r = client.put("/api/account", json={"password": "x"})
    assert r.status_code == 422
    assert r.json()["field"] == "apple_id"
    r = client.put("/api/account", json={"apple_id": " "})
    assert r.status_code == 422
    assert r.json()["field"] == "apple_id"


def test_reauth_not_configured(client: TestClient) -> None:
    r = client.post("/api/account/reauth")
    assert r.status_code == 422
    assert "Settings → Account" in r.json()["error"]


def test_full_reauth_flow(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    configure_account(client)
    started = client.post("/api/account/reauth").json()
    assert started["state"] in ("starting", "awaiting_code")
    wait_until(lambda: attempt_state(client) == "awaiting_code")
    phones = client.get("/api/account/reauth").json()["attempt"]["phones"]
    assert phones == [{"index": "a", "masked": "•••• 12"}]
    assert client.post("/api/account/reauth/code", json={"code": "123456"}).status_code == 200
    wait_until(lambda: client.get("/api/account").json()["state"] == "ok")
    attempts = client.get("/api/account/attempts").json()
    assert attempts[0]["outcome"] == "succeeded"
    log = client.get(f"/api/account/attempts/{attempts[0]['id']}/log")
    assert log.status_code == 200
    assert "Great, you're all set up" in log.text


def test_double_submit_returns_409(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Review Focus #5: a second submit while verifying is a clear 409."""
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    configure_account(client)
    client.post("/api/account/reauth")
    wait_until(lambda: attempt_state(client) == "awaiting_code")
    assert client.post("/api/account/reauth/code", json={"code": "000000"}).status_code == 200
    r = client.post("/api/account/reauth/code", json={"code": "000000"})
    assert r.status_code == 409
    assert "Not waiting" in r.json()["error"]
    wait_until(lambda: attempt_state(client) == "rejected")


def test_code_format_is_validated(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    configure_account(client)
    client.post("/api/account/reauth")
    wait_until(lambda: attempt_state(client) == "awaiting_code")
    r = client.post("/api/account/reauth/code", json={"code": "12ab"})
    assert r.status_code == 422
    assert r.json()["field"] == "code"
    client.delete("/api/account/reauth")


def test_sms_path(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    monkeypatch.setenv("ICLOUDPD_SIM_PHONES", "2")
    configure_account(client)
    client.post("/api/account/reauth")
    wait_until(lambda: attempt_state(client) == "awaiting_code")
    r = client.post("/api/account/reauth/sms", json={"index": "b"})
    assert r.status_code == 200
    assert r.json()["attempt"]["sms_sent_to"] == "•••• 13"
    wait_until(lambda: attempt_state(client) == "awaiting_sms_code")
    client.post("/api/account/reauth/code", json={"code": "123456"})
    wait_until(lambda: client.get("/api/account").json()["state"] == "ok")


def test_restart_and_cancel(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    configure_account(client)
    first = client.post("/api/account/reauth").json()["id"]
    wait_until(lambda: attempt_state(client) == "awaiting_code")
    second = client.post("/api/account/reauth/restart").json()["id"]
    assert second != first
    assert client.delete("/api/account/reauth").json() == {"ok": True}
    assert attempt_state(client) == "cancelled"
    assert client.post("/api/account/reauth/sms", json={"index": "a"}).status_code == 409


def test_attempt_log_cannot_escape(client: TestClient) -> None:
    svc = client.app.state.services  # type: ignore[attr-defined]
    svc.db.save_attempt(
        AuthAttemptRecord(
            id="evil", started_at=datetime.now(UTC), outcome="failed", log_path="/etc/passwd"
        )
    )
    assert client.get("/api/account/attempts/evil/log").status_code == 404
    assert client.get("/api/account/attempts/missing/log").status_code == 404


def test_dismiss_notes(client: TestClient) -> None:
    svc = client.app.state.services  # type: ignore[attr-defined]
    svc.db.kv_set_json("migration_notes", ["hello"])
    assert client.get("/api/account").json()["migration_notes"] == ["hello"]
    client.post("/api/account/dismiss-notes")
    assert client.get("/api/account").json()["migration_notes"] == []
