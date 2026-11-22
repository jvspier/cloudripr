"""One icloudpd subprocess in its own process group, read as raw chunks."""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import os
import signal
from collections.abc import AsyncIterator
from pathlib import Path

from cloudripr.engine.output import OutputEvent, OutputParser


def group_io_bytes(pgid: int, proc_root: Path = Path("/proc")) -> int | None:
    """Sum of rchar+wchar over all processes in group `pgid`, or None if unknown.

    Used as a liveness signal: icloudpd can be silent for a long time while it
    pages through a large library, but it still reads from the network.
    """
    if not proc_root.is_dir():
        return None
    total = 0
    found = False
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            after_comm = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if int(after_comm[2]) != pgid:  # fields: state, ppid, pgrp, ...
                continue
            io_text = (entry / "io").read_text()
        except (OSError, ValueError, IndexError):
            continue
        found = True
        for line in io_text.splitlines():
            key, _, value = line.partition(":")
            if key in ("rchar", "wchar"):
                total += int(value)
    return total if found else None


class IcloudpdProcess:
    def __init__(self, argv: list[str], *, env: dict[str, str] | None = None) -> None:
        self._argv = argv
        self._env = env or {}
        self._proc: asyncio.subprocess.Process | None = None
        self._queue: asyncio.Queue[OutputEvent | None] = asyncio.Queue()
        self._readers: list[asyncio.Task[None]] = []
        self._stdin_closed = False

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc else None

    @property
    def returncode(self) -> int | None:
        return self._proc.returncode if self._proc else None

    async def start(self, *, stdin_text: str | None = None, close_stdin: bool = False) -> None:
        env = {**os.environ, "PYTHONUNBUFFERED": "1", **self._env}
        self._proc = await asyncio.create_subprocess_exec(
            *self._argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        assert self._proc.stdin
        assert self._proc.stdout
        assert self._proc.stderr
        if stdin_text is not None:
            self._proc.stdin.write(stdin_text.encode("utf-8"))
            with contextlib.suppress(ConnectionError):
                await self._proc.stdin.drain()
        if close_stdin:
            self._proc.stdin.close()
            self._stdin_closed = True
        self._readers = [
            asyncio.create_task(self._read(self._proc.stdout)),
            asyncio.create_task(self._read(self._proc.stderr)),
        ]

    async def _read(self, stream: asyncio.StreamReader) -> None:
        parser = OutputParser()
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                for event in parser.feed(decoder.decode(chunk)):
                    await self._queue.put(event)
            for event in parser.feed(decoder.decode(b"", final=True)):
                await self._queue.put(event)
            for event in parser.flush():
                await self._queue.put(event)
        finally:
            await self._queue.put(None)

    async def events(self) -> AsyncIterator[OutputEvent]:
        finished = 0
        while finished < len(self._readers):
            event = await self._queue.get()
            if event is None:
                finished += 1
                continue
            yield event

    async def write_line(self, text: str) -> None:
        if self._proc is None or self._proc.stdin is None or self._stdin_closed:
            raise RuntimeError("stdin is closed")
        self._proc.stdin.write((text + "\n").encode("utf-8"))
        with contextlib.suppress(ConnectionError):
            await self._proc.stdin.drain()

    async def wait(self) -> int:
        assert self._proc is not None
        return await self._proc.wait()

    def _signal_group(self, sig: int) -> None:
        if self._proc is None:
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(self._proc.pid, sig)

    async def terminate(self, grace: float = 10.0) -> int | None:
        if self._proc is None:
            return None
        if self._proc.returncode is None:
            self._signal_group(signal.SIGTERM)
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=grace)
            except TimeoutError:
                self._signal_group(signal.SIGKILL)
                await self._proc.wait()
        # The leader may be gone while a child (the 2FA hook) still runs.
        self._signal_group(signal.SIGKILL)
        return self._proc.returncode

    def io_counter(self) -> int | None:
        if self._proc is None:
            return None
        return group_io_bytes(self._proc.pid)
