from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import AppEnv


def test_first_run_setup_flow(app_env: AppEnv) -> None:
    with TestClient(app_env.build(password=None)) as c:
        assert c.get("/api/auth/status").json() == {"authenticated": False, "setup_required": True}
        assert c.get("/api/events").status_code == 401
        assert c.post("/api/auth/login", json={"password": "x"}).status_code == 409
        r = c.post("/api/auth/setup", json={"password": "short"})
        assert r.status_code == 422
        assert r.json()["field"] == "password"
        assert c.post("/api/auth/setup", json={"password": "long-enough"}).status_code == 200
        assert c.get("/api/auth/status").json() == {"authenticated": True, "setup_required": False}
        assert c.post("/api/auth/setup", json={"password": "again-again"}).status_code == 409


def test_login_logout(app_env: AppEnv) -> None:
    with TestClient(app_env.build()) as c:
        assert c.get("/api/auth/status").json()["authenticated"] is False
        r = c.post("/api/auth/login", json={"password": "wrong-one"})
        assert r.status_code == 401
        assert r.json()["error"] == "Wrong password."
        assert c.post("/api/auth/login", json={"password": "long-enough"}).status_code == 200
        assert c.get("/api/auth/status").json()["authenticated"] is True
        c.post("/api/auth/logout")
        assert c.get("/api/auth/status").json()["authenticated"] is False


def test_login_rate_limited(app_env: AppEnv) -> None:
    with TestClient(app_env.build()) as c:
        for _ in range(5):
            assert c.post("/api/auth/login", json={"password": "bad"}).status_code == 401
        r = c.post("/api/auth/login", json={"password": "long-enough"})
        assert r.status_code == 429


def test_concurrent_http_setup_authenticates_only_the_winner(app_env: AppEnv) -> None:
    from concurrent.futures import ThreadPoolExecutor

    app = app_env.build(password=None)
    with TestClient(app) as c:

        def attempt(i: int) -> tuple[int, TestClient]:
            client = TestClient(app)
            r = client.post("/api/auth/setup", json={"password": f"password-{i}"})
            return r.status_code, client

        with ThreadPoolExecutor(8) as pool:
            results = list(pool.map(attempt, range(8)))
        assert sorted(s for s, _ in results) == [200] + [409] * 7
        assert [cl.get("/api/auth/status").json()["authenticated"] for _, cl in results].count(
            True
        ) == 1
        del c


def test_concurrent_wrong_logins_are_limited(app_env: AppEnv) -> None:
    from concurrent.futures import ThreadPoolExecutor

    app = app_env.build()
    with TestClient(app) as c:

        def attempt(_: int) -> int:
            return c.post("/api/auth/login", json={"password": "bad"}).status_code

        with ThreadPoolExecutor(30) as pool:
            codes = list(pool.map(attempt, range(30)))
        assert codes.count(401) == 5
        assert codes.count(429) == 25


def test_unknown_api_paths_and_methods_use_error_contract(client: TestClient) -> None:
    for method in ("POST", "DELETE", "PUT", "GET"):
        r = client.request(method, "/api/nope")
        assert r.status_code == 404
        assert r.json()["error"] == "Not found"
    r = client.delete("/api/auth/status")
    assert r.status_code == 405
    assert r.json()["error"]


def test_api_schema_not_served(app_env: AppEnv) -> None:
    with TestClient(app_env.build()) as c:
        for path in ("/docs", "/redoc", "/openapi.json"):
            r = c.get(path)
            assert "openapi" not in r.text.lower()
