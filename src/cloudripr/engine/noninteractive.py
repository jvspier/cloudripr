"""Unattended icloudpd: password then EOF, 2FA hook armed, hang watchdog."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cloudripr.engine.hook import MARKER_ENV, new_marker
from cloudripr.engine.logwriter import LogWriter
from cloudripr.engine.output import OutputEvent
from cloudripr.engine.process import IcloudpdProcess


_ERROR_PREFIX = re.compile(r"^(?:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s+)?ERROR\s+")


@dataclass
class NonInteractiveResult:
    exit_code: int | None
    twofa_required: bool = False
    bad_password: bool = False
    idle_timeout: bool = False
    stopped: bool = False
    hook_fired: bool = False
    spawn_error: str | None = None
    last_error: str | None = None


class NonInteractiveRun:
    def __init__(
        self,
        argv: list[str],
        *,
        password: str,
        log: LogWriter,
        hook_script: Path,
        marker_dir: Path,
        idle_timeout: float,
        on_event: Callable[[OutputEvent], None] | None = None,
        poll_interval: float = 1.0,
        grace: float = 10.0,
        kill_on_twofa_line: bool = True,
    ) -> None:
        self._argv = argv
        self._password = password
        self._log = log
        self._hook = hook_script
        self._marker_dir = marker_dir
        self._idle_timeout = idle_timeout
        self._on_event = on_event
        self._poll = poll_interval
        self._grace = grace
        self._kill_on_twofa_line = kill_on_twofa_line
        self._stop_requested = False
        self._proc: IcloudpdProcess | None = None

    async def stop(self) -> None:
        self._stop_requested = True

    async def run(self) -> NonInteractiveResult:  # noqa: C901
        loop = asyncio.get_running_loop()
        self._marker_dir.mkdir(parents=True, exist_ok=True)
        marker = new_marker(self._marker_dir)
        argv = [*self._argv, "--notification-script", str(self._hook)]
        proc = IcloudpdProcess(argv, env={MARKER_ENV: str(marker)})
        self._proc = proc
        result = NonInteractiveResult(exit_code=None)
        try:
            await proc.start(stdin_text=self._password + "\n", close_stdin=True)
        except OSError as exc:
            result.spawn_error = str(exc)
            self._log.write(f"ERROR    Could not start icloudpd: {exc}")
            return result

        twofa_seen = asyncio.Event()
        last_activity = loop.time()
        last_io = proc.io_counter()

        async def pump() -> None:
            nonlocal last_activity
            async for event in proc.events():
                last_activity = loop.time()
                if event.kind == "line":
                    self._log.write(event.text)
                    if _ERROR_PREFIX.match(event.text):
                        result.last_error = _ERROR_PREFIX.sub("", event.text).strip()
                elif event.kind in ("twofa_required", "prompt"):
                    result.twofa_required = True
                    if event.kind == "twofa_required":
                        twofa_seen.set()
                elif event.kind == "bad_password":
                    result.bad_password = True
                if self._on_event is not None:
                    self._on_event(event)

        pump_task = asyncio.create_task(pump())
        try:
            while not pump_task.done():
                twofa_task = asyncio.create_task(twofa_seen.wait())
                try:
                    await asyncio.wait(
                        {pump_task, twofa_task},
                        timeout=self._poll,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                finally:
                    twofa_task.cancel()
                if pump_task.done():
                    break
                if self._kill_on_twofa_line and twofa_seen.is_set():
                    self._log.write(
                        "WARNING  Apple requires two-factor authentication; "
                        "stopped before any code was requested."
                    )
                    await proc.terminate(self._grace)
                    break
                if marker.exists():
                    result.hook_fired = True
                    result.twofa_required = True
                    self._log.write(
                        "WARNING  Apple requires two-factor authentication; "
                        "stopping before any code is requested."
                    )
                    await proc.terminate(self._grace)
                    break
                if self._stop_requested:
                    result.stopped = True
                    self._log.write("WARNING  Stopped by the user.")
                    await proc.terminate(self._grace)
                    break
                io = proc.io_counter()
                if io is not None and io != last_io:
                    last_io = io
                    last_activity = loop.time()
                if loop.time() - last_activity > self._idle_timeout:
                    result.idle_timeout = True
                    self._log.write(
                        f"WARNING  No activity for {int(self._idle_timeout)} seconds; stopping."
                    )
                    await proc.terminate(self._grace)
                    break
            await pump_task
            result.exit_code = await proc.wait()
        finally:
            marker.unlink(missing_ok=True)
            await proc.terminate(0.5)
        return result
