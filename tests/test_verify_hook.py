from __future__ import annotations

from pathlib import Path

import pytest

from cloudripr.tools import verify_hook as vh
from tests.helpers import SIM_CMD


async def check(tmp_path: Path) -> tuple[bool, str]:
    return await vh.verify_hook(
        icloudpd_cmd=SIM_CMD,
        apple_id="me@example.com",
        domain="com",
        password="pw",
        work_dir=tmp_path,
        poll_interval=0.05,
    )


async def test_protected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    ok, message = await check(tmp_path)
    assert ok is True
    assert message.startswith("OK")


async def test_hook_that_does_nothing_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")

    def broken_install(path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
        return path

    monkeypatch.setattr(vh, "install_hook", broken_install)
    ok, message = await check(tmp_path)
    assert ok is False
    assert message.startswith("FAILED")


async def test_no_2fa_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "ok")
    ok, message = await check(tmp_path)
    assert ok is False
    assert "did not ask" in message


async def test_bad_password(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "bad_password")
    ok, message = await check(tmp_path)
    assert ok is False
    assert "password" in message


async def test_inconclusive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "fail")
    ok, message = await check(tmp_path)
    assert ok is False
    assert message.startswith("Inconclusive")


def test_cli_wires_through(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from cloudripr import cli

    async def fake(**kwargs: object) -> tuple[bool, str]:
        assert kwargs["apple_id"] == "me@example.com"
        assert kwargs["password"] == "pw"
        return True, "OK: fine"

    monkeypatch.setattr("cloudripr.tools.verify_hook.verify_hook", fake)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "pw")
    assert cli.main(["verify-2fa-hook", "--apple-id", "me@example.com"]) == 0
    assert "OK: fine" in capsys.readouterr().out
