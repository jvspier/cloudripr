from __future__ import annotations

from pathlib import Path

import pytest

from cloudripr.engine.hook import install_hook
from cloudripr.engine.logwriter import LogWriter
from cloudripr.engine.noninteractive import NonInteractiveRun
from cloudripr.engine.output import OutputEvent
from tests.helpers import SIM_CMD


def make_run(
    tmp_path: Path,
    *extra: str,
    idle: float = 30.0,
    events: list[OutputEvent] | None = None,
    kill_on_twofa_line: bool = True,
    broken_hook: bool = False,
    create_markers: bool = True,
) -> tuple[NonInteractiveRun, Path]:
    hook = install_hook(tmp_path / "bin" / "2fa-hook")
    if broken_hook:
        hook.write_text("#!/bin/sh\nsleep 0.5\nexit 0\n")
    markers = tmp_path / "markers"
    if create_markers:
        markers.mkdir(exist_ok=True)
    log_path = tmp_path / "run.log"
    argv = [
        *SIM_CMD,
        "--username",
        "u@example.com",
        "--password-provider",
        "console",
        "--mfa-provider",
        "console",
        "--directory",
        str(tmp_path / "lib"),
        *extra,
    ]
    run = NonInteractiveRun(
        argv,
        password="pw",
        kill_on_twofa_line=kill_on_twofa_line,
        log=LogWriter(log_path),
        hook_script=hook,
        marker_dir=markers,
        idle_timeout=idle,
        on_event=(events.append if events is not None else None),
        poll_interval=0.05,
        grace=2.0,
    )
    return run, log_path


async def test_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "ok")
    events: list[OutputEvent] = []
    run, log_path = make_run(tmp_path, events=events)
    res = await run.run()
    assert res.exit_code == 0
    assert not res.twofa_required
    assert not res.idle_timeout
    assert sum(e.kind == "downloaded" for e in events) == 2
    assert "Downloaded" in log_path.read_text()


async def test_twofa_is_stopped_by_hook_before_any_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    run, log_path = make_run(tmp_path, kill_on_twofa_line=False)
    res = await run.run()
    assert res.twofa_required is True
    assert res.hook_fired is True
    assert res.exit_code != 0
    text = log_path.read_text()
    # The simulator prints the phone list and prompt only AFTER the hook returns,
    # which is where upstream requests the push. Neither may appear.
    assert "Please enter" not in text
    assert "•••" not in text
    assert list((tmp_path / "markers").iterdir()) == []


async def test_twofa_line_kill_protects_even_with_broken_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    run, log_path = make_run(tmp_path, broken_hook=True)
    res = await run.run()
    assert res.twofa_required is True
    text = log_path.read_text()
    assert "Please enter" not in text
    assert "•••" not in text


async def test_missing_marker_dir_is_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    run, log_path = make_run(tmp_path, create_markers=False, kill_on_twofa_line=False)
    res = await run.run()
    assert (tmp_path / "markers").is_dir()
    assert res.hook_fired is True
    text = log_path.read_text()
    assert "Please enter" not in text
    assert "•••" not in text


async def test_bad_password(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "bad_password")
    run, _ = make_run(tmp_path)
    res = await run.run()
    assert res.bad_password is True
    assert res.exit_code == 1


async def test_failure_reports_last_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "fail")
    run, _ = make_run(tmp_path)
    res = await run.run()
    assert res.exit_code == 2
    assert res.last_error == "something went wrong"


async def test_idle_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "silent")
    monkeypatch.setenv("ICLOUDPD_SIM_SECONDS", "10")
    run, log_path = make_run(tmp_path, idle=0.4)
    res = await run.run()
    assert res.idle_timeout is True
    assert "No activity" in log_path.read_text()


@pytest.mark.skipif(not Path("/proc/self/io").exists(), reason="needs Linux /proc")
async def test_io_activity_counts_as_alive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "busy_silent")
    monkeypatch.setenv("ICLOUDPD_SIM_SECONDS", "1.5")
    run, _ = make_run(tmp_path, idle=0.6)
    res = await run.run()
    assert res.idle_timeout is False
    assert res.exit_code == 0


async def test_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "silent")
    monkeypatch.setenv("ICLOUDPD_SIM_SECONDS", "10")
    run, _ = make_run(tmp_path)
    task = asyncio.create_task(run.run())
    await asyncio.sleep(0.3)
    await run.stop()
    res = await task
    assert res.stopped is True


async def test_spawn_error(tmp_path: Path) -> None:
    hook = install_hook(tmp_path / "hook")
    run = NonInteractiveRun(
        ["/nonexistent/icloudpd"],
        password="pw",
        log=LogWriter(tmp_path / "r.log"),
        hook_script=hook,
        marker_dir=tmp_path,
        idle_timeout=5,
    )
    res = await run.run()
    assert res.spawn_error is not None
    assert res.exit_code is None
