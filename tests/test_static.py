from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cloudripr.errors import install_handlers
from cloudripr.static import install_static


def make_dist(tmp_path: Path, *, assets: bool = True) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><html>app</html>")
    (dist / "robots.txt").write_text("User-agent: *")
    if assets:
        (dist / "assets").mkdir()
        (dist / "assets" / "main.js").write_text("console.log('x');")
    return dist


def client(static_dir: Path | None) -> TestClient:
    app = FastAPI()
    install_handlers(app)
    install_static(app, static_dir)
    return TestClient(app)


def test_index_assets_files_and_fallback(tmp_path: Path) -> None:
    c = client(make_dist(tmp_path))
    assert "<html>app</html>" in c.get("/").text
    assert "console.log" in c.get("/assets/main.js").text
    assert "User-agent" in c.get("/robots.txt").text
    assert "<html>app</html>" in c.get("/account/reauth").text  # SPA route


def test_no_assets_dir(tmp_path: Path) -> None:
    assert "<html>app</html>" in client(make_dist(tmp_path, assets=False)).get("/").text


def test_encoded_traversal_falls_back_to_index(tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("SECRETDATA")
    c = client(make_dist(tmp_path))
    for attempt in ["/%2e%2e/secret.txt", "/%2E%2E%2Fsecret.txt", "/%2e%2e%2fsecret.txt"]:
        r = c.get(attempt)
        assert "SECRETDATA" not in r.text
        assert "<html>app</html>" in r.text


def test_unknown_api_paths_are_json_404(tmp_path: Path) -> None:
    for c in (client(make_dist(tmp_path)), client(None)):
        r = c.get("/api/nope")
        assert r.status_code == 404
        assert r.json()["error"] == "Not found"
        assert c.get("/api").status_code == 404


def test_placeholder_without_build(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    for c in (client(None), client(empty)):
        assert "not built" in c.get("/").text.lower()
