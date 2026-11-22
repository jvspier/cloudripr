from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

from cloudripr.engine.hook import HOOK_SCRIPT, MARKER_ENV, install_hook, new_marker


def test_install_hook_is_executable_and_idempotent(tmp_path: Path) -> None:
    path = install_hook(tmp_path / "bin" / "2fa-hook")
    assert path.read_text() == HOOK_SCRIPT
    assert os.access(path, os.X_OK)
    install_hook(path)
    assert path.read_text() == HOOK_SCRIPT
    assert MARKER_ENV in HOOK_SCRIPT


def test_new_marker_is_unique_and_not_created(tmp_path: Path) -> None:
    a, b = new_marker(tmp_path), new_marker(tmp_path)
    assert a != b
    assert a.parent == tmp_path
    assert not a.exists()


def test_hook_does_not_exit_when_marker_cannot_be_created(tmp_path: Path) -> None:
    path = install_hook(tmp_path / "hook")
    env = {**os.environ, MARKER_ENV: str(tmp_path / "missing" / "m")}
    proc = subprocess.Popen([str(path)], env=env, start_new_session=True)  # noqa: S603
    try:
        time.sleep(1)
        assert proc.poll() is None
    finally:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
