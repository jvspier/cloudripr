from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from cloudripr.services import Services
from cloudripr.store.db import RunRecord
from cloudripr.store.models import Policy
from tests.api.conftest import AppEnv


NOV = datetime(2026, 11, 15, 12).timestamp()


@pytest.fixture
def lib(tmp_path: Path) -> Path:
    root = tmp_path / "photos"
    (root / "2026/11").mkdir(parents=True)
    Image.new("RGB", (800, 600), (9, 9, 9)).save(root / "2026/11/GOOD.JPG")
    (root / "2026/11/BAD.HEIC").write_bytes(b"\0" * 64)
    (root / "2026/11/CLIP.MP4").write_bytes(bytes(range(256)) * 4)
    for f in (root / "2026/11").iterdir():
        os.utime(f, (NOV, NOV))
    return root


@pytest.fixture
def env(app_env: AppEnv, lib: Path) -> Iterator[tuple[TestClient, Services]]:
    app = app_env.build()
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"password": "long-enough"}).status_code == 200
        svc: Services = app.state.services
        svc.library.scan(lib)
        yield c, svc


def item_id(svc: Services, name: str) -> int:
    return next(i.id for i in svc.library.items_in_month("2026-11") if i.rel.endswith(name))


def test_requires_login(app_env: AppEnv) -> None:
    with TestClient(app_env.build()) as c:
        assert c.get("/api/library/summary").status_code == 401


def test_summary_and_months(env: tuple[TestClient, Services], lib: Path) -> None:
    c, svc = env
    assert c.get("/api/library/summary").json()["icloud"] is None
    svc.policies.put(Policy(name="p", username="me@example.com", directory=lib, cron="0 3 * * *"))  # type: ignore[arg-type]
    svc.db.kv_set_json("icloud_total:p", {"count": 5, "seen_at": "2026-11-22T03:00:00+00:00"})
    summary = c.get("/api/library/summary").json()
    assert summary["on_disk"] == 3
    assert summary["unreadable"] == 0
    assert summary["scanned_at"]
    assert summary["icloud"] == {"count": 5, "seen_at": "2026-11-22T03:00:00+00:00"}
    assert c.get("/api/library/months").json() == [
        {"month": "2026-11", "count": 3, "unreadable": 0}
    ]


def test_items_by_month_and_by_run(env: tuple[TestClient, Services], lib: Path) -> None:
    c, svc = env
    month = c.get("/api/library/items", params={"month": "2026-11"}).json()
    assert sorted(i["name"] for i in month) == ["BAD.HEIC", "CLIP.MP4", "GOOD.JPG"]
    good = next(i for i in month if i["name"] == "GOOD.JPG")
    assert good["folder"] == "2026/11"
    assert good["kind"] == "photo"
    assert good["run_id"] is None
    assert good["taken_at"].startswith("2026-11-15")
    svc.db.save_run(
        RunRecord(
            id="r1", policy="p", trigger="schedule", status="success",
            started_at=datetime(2026, 11, 22, 3, tzinfo=UTC), downloaded=1,
        )
    )  # fmt: skip
    svc.db.add_run_files("r1", [str(lib / "2026/11/GOOD.JPG")])
    by_run = c.get("/api/library/items", params={"run": "r1"}).json()
    assert [(i["name"], i["run_id"]) for i in by_run] == [("GOOD.JPG", "r1")]
    runs = c.get("/api/library/runs").json()
    assert runs[0]["run"]["id"] == "r1"
    assert runs[0]["count"] == 1
    assert [s["name"] for s in runs[0]["sample"]] == ["GOOD.JPG"]


def test_items_needs_exactly_one_filter(env: tuple[TestClient, Services]) -> None:
    c, _ = env
    assert c.get("/api/library/items").status_code == 422
    assert c.get("/api/library/items", params={"month": "2026-11", "run": "r1"}).status_code == 422
    assert c.get("/api/library/items", params={"month": "nope"}).status_code == 422


def test_thumb_served_and_cached_headers(env: tuple[TestClient, Services]) -> None:
    c, svc = env
    r = c.get(f"/api/library/items/{item_id(svc, 'GOOD.JPG')}/thumb")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert "immutable" in r.headers["cache-control"]
    assert c.get(f"/api/library/items/{item_id(svc, 'GOOD.JPG')}/preview").status_code == 200


def test_thumb_of_unreadable_file_is_404_and_marked(env: tuple[TestClient, Services]) -> None:
    c, svc = env
    bad = item_id(svc, "BAD.HEIC")
    assert c.get(f"/api/library/items/{bad}/thumb").status_code == 404
    item = svc.library.get(bad)
    assert item is not None
    assert item.problem
    assert c.get("/api/library/summary").json()["unreadable"] == 1


def test_deleted_file_is_404(env: tuple[TestClient, Services], lib: Path) -> None:
    c, svc = env
    good = item_id(svc, "GOOD.JPG")
    (lib / "2026/11/GOOD.JPG").unlink()
    assert c.get(f"/api/library/items/{good}/original").status_code == 404
    assert c.get(f"/api/library/items/{good}/thumb").status_code == 404
    assert c.get("/api/library/items/999999/thumb").status_code == 404


def test_original_refuses_path_outside_root(
    env: tuple[TestClient, Services], lib: Path, tmp_path: Path
) -> None:
    c, svc = env
    secret = tmp_path / "secret.JPG"
    Image.new("RGB", (10, 10)).save(secret)
    (lib / "2026/11/LINK.JPG").symlink_to(secret)
    svc.library.scan(lib)
    link = item_id(svc, "LINK.JPG")
    assert c.get(f"/api/library/items/{link}/original").status_code == 404
    assert c.get(f"/api/library/items/{link}/thumb").status_code == 404


def test_original_supports_range(env: tuple[TestClient, Services]) -> None:
    c, svc = env
    r = c.get(
        f"/api/library/items/{item_id(svc, 'CLIP.MP4')}/original", headers={"Range": "bytes=0-9"}
    )
    assert r.status_code == 206
    assert r.content == bytes(range(10))
    assert r.headers["content-type"] == "video/mp4"
