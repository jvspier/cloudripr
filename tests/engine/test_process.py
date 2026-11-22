from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path

import pytest

from cloudripr.engine.output import OutputEvent
from cloudripr.engine.process import IcloudpdProcess, group_io_bytes
from tests.helpers import SIM_CMD, eventually


def argv(*extra: str) -> list[str]:
    return [
        *SIM_CMD,
        "--username",
        "u@example.com",
        "--password-provider",
        "console",
        "--mfa-provider",
        "console",
        *extra,
    ]


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def collect(proc: IcloudpdProcess) -> list[OutputEvent]:
    return [e async for e in proc.events()]


async def test_download_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "ok")
    proc = IcloudpdProcess(argv("--directory", str(tmp_path)))
    await proc.start(stdin_text="pw\n", close_stdin=True)
    events = await collect(proc)
    assert await proc.wait() == 0
    downloaded = [e.value for e in events if e.kind == "downloaded"]
    assert downloaded == [
        str(tmp_path / "2026/10/IMG_0001.HEIC"),
        str(tmp_path / "2026/10/IMG_0002.HEIC"),
    ]
    assert (tmp_path / "2026/10/IMG_0002.HEIC").is_file()


async def test_closed_stdin_ends_a_prompt_with_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    proc = IcloudpdProcess(argv("--auth-only"))
    await proc.start(stdin_text="pw\n", close_stdin=True)
    events = await collect(proc)
    assert await proc.wait() != 0
    assert any(e.kind == "prompt" for e in events)


async def test_interactive_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    proc = IcloudpdProcess(argv("--auth-only"))
    await proc.start(stdin_text="pw\n")
    seen: list[str] = []
    async for e in proc.events():
        seen.append(e.kind)
        if e.kind == "prompt":
            await proc.write_line("123456")
    assert await proc.wait() == 0
    assert "auth_ok" in seen


async def test_write_line_after_close_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "ok")
    proc = IcloudpdProcess(argv("--auth-only"))
    await proc.start(stdin_text="pw\n", close_stdin=True)
    with pytest.raises(RuntimeError):
        await proc.write_line("x")
    await collect(proc)
    await proc.wait()


async def test_terminate_kills_whole_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pidfile = tmp_path / "hook.pid"
    script = tmp_path / "hook"
    script.write_text(f"#!/bin/sh\necho $$ > {pidfile}\nexec sleep 30\n")
    script.chmod(0o755)
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")
    proc = IcloudpdProcess(argv("--auth-only", "--notification-script", str(script)))
    await proc.start(stdin_text="pw\n")
    await eventually(lambda: pidfile.exists() and pidfile.read_text().strip() != "")
    hook_pid = int(pidfile.read_text())
    pgid = proc.pid
    assert pgid is not None
    assert pid_alive(hook_pid)
    await proc.terminate(grace=2.0)
    # Zombies are reaped asynchronously, so poll.
    await eventually(lambda: not pid_alive(hook_pid))

    def group_gone() -> bool:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        return False

    await eventually(group_gone, timeout=5.0)


async def test_terminate_escalates_to_sigkill() -> None:
    proc = IcloudpdProcess(["/bin/sh", "-c", "trap '' TERM; echo ready; sleep 30"])
    await proc.start(close_stdin=True)
    async for e in proc.events():
        if e.text == "ready":
            break
    assert await proc.terminate(grace=0.3) == -signal.SIGKILL


async def test_terminate_sweeps_leftover_group_members() -> None:
    proc = IcloudpdProcess(["/bin/sh", "-c", "sleep 30 & echo $!; exit 0"])
    await proc.start(close_stdin=True)
    child = 0
    async for e in proc.events():
        if e.kind == "line" and e.text.strip().isdigit():
            child = int(e.text.strip())
            break
    assert child > 0
    # proc.wait() would block until the orphan closes the inherited pipes.
    await eventually(lambda: proc.returncode is not None)
    assert pid_alive(child)
    await proc.terminate()
    await eventually(lambda: not pid_alive(child))


async def test_multibyte_char_split_across_reads_stays_intact() -> None:
    proc = IcloudpdProcess([])
    stream = asyncio.StreamReader()
    raw = "  a: (\u2022\u2022\u2022) done\n".encode()
    cut = raw.index("\u2022".encode()) + 1  # inside the first bullet
    reader = asyncio.create_task(proc._read(stream))  # noqa: SLF001
    stream.feed_data(raw[:cut])
    await eventually(lambda: not stream._buffer)  # noqa: SLF001 - first read consumed
    await asyncio.sleep(0.05)
    stream.feed_data(raw[cut:])
    stream.feed_eof()
    await reader
    events = []
    while not proc._queue.empty():  # noqa: SLF001
        if (event := proc._queue.get_nowait()) is not None:  # noqa: SLF001
            events.append(event)
    text = "".join(e.text for e in events)
    assert "\u2022\u2022\u2022" in text
    assert "\ufffd" not in text


async def test_spawn_failure_raises_oserror() -> None:
    proc = IcloudpdProcess(["/nonexistent/icloudpd"])
    with pytest.raises(OSError):  # noqa: PT011 - errno message is platform-specific
        await proc.start()


def test_group_io_bytes_from_fake_proc(tmp_path: Path) -> None:
    def fake(pid: int, pgrp: int, rchar: int, wchar: int) -> None:
        d = tmp_path / str(pid)
        d.mkdir()
        (d / "stat").write_text(f"{pid} (python3 x) S 1 {pgrp} {pgrp} 0 -1\n")
        (d / "io").write_text(f"rchar: {rchar}\nwchar: {wchar}\nsyscr: 1\n")

    fake(10, 999, 100, 5)
    fake(11, 999, 1, 1)
    fake(12, 123, 50, 50)
    (tmp_path / "self").mkdir()
    assert group_io_bytes(999, tmp_path) == 107
    assert group_io_bytes(555, tmp_path) is None
    assert group_io_bytes(999, tmp_path / "missing") is None


@pytest.mark.skipif(not Path("/proc/self/io").exists(), reason="needs Linux /proc")
async def test_io_counter_on_live_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "silent")
    monkeypatch.setenv("ICLOUDPD_SIM_SECONDS", "1")
    proc = IcloudpdProcess(argv())
    await proc.start(stdin_text="pw\n", close_stdin=True)
    assert isinstance(proc.io_counter(), int)
    await proc.terminate(grace=1.0)
