from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cloudripr.app import create_app
from cloudripr.auth import Authenticator
from cloudripr.paths import DataPaths
from tests.helpers import SIM_CMD, FakeSender


@dataclass
class AppEnv:
    paths: DataPaths
    sender: FakeSender
    build: Callable[..., FastAPI]


@pytest.fixture
def app_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppEnv:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "ok")
    paths = DataPaths(tmp_path / "data", tmp_path / "cache")
    sender = FakeSender()

    def build(*, password: str | None = "long-enough", start_scheduler: bool = False) -> FastAPI:
        paths.ensure()
        auth = Authenticator(
            Authenticator.hash(password) if password else None, hash_file=paths.app / "login.hash"
        )
        return create_app(
            paths=paths,
            authenticator=auth,
            session_secret="s" * 32,
            icloudpd_cmd=SIM_CMD,
            icloudpd_version="1.32.3",
            sender=sender,
            start_scheduler=start_scheduler,
            poll_interval=0.05,
        )

    return AppEnv(paths, sender, build)


@pytest.fixture
def client(app_env: AppEnv) -> Iterator[TestClient]:
    with TestClient(app_env.build()) as c:
        assert c.post("/api/auth/login", json={"password": "long-enough"}).status_code == 200
        yield c


def configure_account(
    client: TestClient, apple_id: str = "me@example.com", password: str = "pw"
) -> None:
    r = client.put("/api/account", json={"apple_id": apple_id, "password": password})
    assert r.status_code == 200, r.text
