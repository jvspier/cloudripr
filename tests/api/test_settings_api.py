import tomllib

from fastapi.testclient import TestClient

from tests.api.conftest import AppEnv


EMAIL = {
    "to": "me@example.com",
    "smtp_user": "bot@example.com",
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "smtp_security": "starttls",
    "extra_urls": [],
    "on_failure": True,
    "on_success": False,
    "app_url": "http://nas:5000",
}


def put(client: TestClient, **changes: object) -> dict:
    current = client.get("/api/settings").json()
    current.pop("smtp_password_set")
    current.pop("email_last_error")
    current.update(changes)
    r = client.put("/api/settings", json=current)
    assert r.status_code == 200, r.text
    return r.json()


def test_defaults(client: TestClient) -> None:
    data = client.get("/api/settings").json()
    assert data["retention_runs"] == 30
    assert data["session_check_time"] == "19:00"
    assert data["smtp_password_set"] is False
    assert "apprise" not in data


def test_smtp_password_is_write_only(client: TestClient, app_env: AppEnv) -> None:
    data = put(client, email=EMAIL, smtp_password="hunter2")
    assert data["smtp_password_set"] is True
    assert "hunter2" not in str(data)
    assert (app_env.paths.secrets / "_smtp.password").read_text() == "hunter2"
    assert put(client, retention_runs=40)["smtp_password_set"] is True  # kept
    assert put(client, smtp_password="")["smtp_password_set"] is False  # cleared


def test_validation_shape(client: TestClient) -> None:
    current = client.get("/api/settings").json()
    current["session_check_time"] = "25:00"
    r = client.put("/api/settings", json=current)
    assert r.status_code == 422
    assert r.json()["field"] == "session_check_time"


def test_test_email(client: TestClient, app_env: AppEnv) -> None:
    assert client.post("/api/settings/test-email").json() == {
        "ok": False,
        "error": "Email is not set up yet.",
    }
    put(client, email=EMAIL, smtp_password="pw")
    assert client.post("/api/settings/test-email").json() == {"ok": True, "error": None}
    assert app_env.sender.titles == ["Test email from cloudripr"]


def test_legacy_apprise_table_survives(client: TestClient, app_env: AppEnv) -> None:
    svc = client.app.state.services  # type: ignore[attr-defined]
    svc.settings.current.apprise = {"urls": ["json://x"]}
    put(client, retention_runs=12)
    on_disk = tomllib.loads(app_env.paths.settings_file.read_text())
    assert on_disk["apprise"] == {"urls": ["json://x"]}
