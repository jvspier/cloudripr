"""One interactive `icloudpd --auth-only` attempt."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from cloudripr.engine.logwriter import LogWriter
from cloudripr.engine.process import IcloudpdProcess


AttemptState = Literal[
    "starting",
    "awaiting_code",
    "sending_sms",
    "awaiting_sms_code",
    "verifying",
    "succeeded",
    "rejected",
    "bad_password",
    "expired",
    "cancelled",
    "failed",
]
FINAL_ATTEMPT_STATES: frozenset[str] = frozenset(
    {"succeeded", "rejected", "bad_password", "expired", "cancelled", "failed"}
)
CODE_RE = re.compile(r"^\d{6}$")
_ERROR_PREFIX = re.compile(r"^(?:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s+)?ERROR\s+")


class AttemptError(Exception):
    """The user asked for something this attempt can't do right now."""


@dataclass(frozen=True)
class PhoneOption:
    index: str
    masked: str


def mask_phone(text: str) -> str:
    digits = re.findall(r"\d", text)
    return f"•••• {''.join(digits[-2:])}" if digits else "••••"


class ReauthAttempt:
    def __init__(
        self,
        *,
        attempt_id: str,
        argv: list[str],
        password: str,
        log: LogWriter,
        timeout: float = 600.0,
        on_change: Callable[[ReauthAttempt], None] | None = None,
    ) -> None:
        self.id = attempt_id
        self.state: AttemptState = "starting"
        self.phones: list[PhoneOption] = []
        self.error: str | None = None
        self.sms_sent_to: str | None = None
        self.started_at = datetime.now(UTC)
        self.ended_at: datetime | None = None
        self.log_path = log.path
        self._argv = argv
        self._password = password
        self._log = log
        self._timeout = timeout
        self._on_change = on_change
        self._proc: IcloudpdProcess | None = None
        self._pump_task: asyncio.Task[None] | None = None
        self._timer_task: asyncio.Task[None] | None = None
        self._done = asyncio.Event()

    @property
    def finished(self) -> bool:
        return self.state in FINAL_ATTEMPT_STATES

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "state": self.state,
            "phones": [{"index": p.index, "masked": p.masked} for p in self.phones],
            "error": self.error,
            "sms_sent_to": self.sms_sent_to,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }

    async def start(self) -> None:
        if self.finished:
            return  # cancelled while waiting for the account lock
        self._proc = IcloudpdProcess(self._argv)
        try:
            await self._proc.start(stdin_text=self._password + "\n")
        except OSError as exc:
            self._finish("failed", f"Could not start icloudpd: {exc}")
            return
        if self.finished:  # cancelled while the process was starting
            await self._proc.terminate(2.0)
            return
        self._pump_task = asyncio.create_task(self._pump())
        self._timer_task = asyncio.create_task(self._expire_later())

    async def _pump(self) -> None:
        assert self._proc is not None
        rejected = bad_password = False
        last_error: str | None = None
        async for event in self._proc.events():
            if event.kind == "line":
                self._log.write(event.text)
                if _ERROR_PREFIX.match(event.text):
                    last_error = _ERROR_PREFIX.sub("", event.text).strip()
            elif event.kind == "phone_option" and event.value:
                self.phones.append(PhoneOption(event.value, mask_phone(event.text)))
            elif event.kind == "prompt" and not self.finished:
                self._set("awaiting_sms_code" if event.value == "sms_code" else "awaiting_code")
            elif event.kind == "mfa_rejected":
                rejected = True
            elif event.kind == "bad_password":
                bad_password = True
        self._finish_from_exit(await self._proc.wait(), rejected, bad_password, last_error)

    def _finish_from_exit(
        self, code: int | None, rejected: bool, bad_password: bool, last_error: str | None
    ) -> None:
        if code == 0:
            self._finish("succeeded")
        elif bad_password:
            self._finish(
                "bad_password",
                "Apple rejected the Apple ID password. Update it under Settings → Account.",
            )
        elif rejected:
            self._finish("rejected", "Apple rejected that code.")
        else:
            self._finish("failed", last_error or f"icloudpd stopped unexpectedly (exit {code}).")

    async def _expire_later(self) -> None:
        await asyncio.sleep(self._timeout)
        if not self.finished:
            self._finish("expired", "The sign-in timed out. Start over to get a new code.")
            if self._proc is not None:
                await self._proc.terminate(2.0)

    async def submit_code(self, code: str) -> None:
        code = code.strip()
        if self.state not in ("awaiting_code", "awaiting_sms_code"):
            raise AttemptError("Not waiting for a code right now.")
        if not CODE_RE.match(code):
            raise AttemptError("Enter the 6-digit code.")
        self._set("verifying")
        await self._write(code)

    async def request_sms(self, index: str) -> None:
        if self.state != "awaiting_code":
            raise AttemptError("Not waiting for a code right now.")
        phone = next((p for p in self.phones if p.index == index), None)
        if phone is None:
            raise AttemptError("Unknown phone number.")
        self.sms_sent_to = phone.masked
        self._set("sending_sms")
        await self._write(index)

    async def _write(self, text: str) -> None:
        assert self._proc is not None
        try:
            await self._proc.write_line(text)
        except RuntimeError as exc:
            raise AttemptError("icloudpd is no longer running. Start over.") from exc

    async def cancel(self) -> None:
        if self.finished:
            return
        self._finish("cancelled")
        if self._proc is not None:
            await self._proc.terminate(2.0)

    async def abort(self, reason: str) -> None:
        if self.finished:
            return
        self._finish("failed", reason)
        if self._proc is not None:
            await self._proc.terminate(2.0)

    async def wait(self) -> str:
        await self._done.wait()
        if self._timer_task is not None and not self._timer_task.done():
            self._timer_task.cancel()
        if self._proc is not None:  # never wait on a pump stuck at a code prompt
            await self._proc.terminate(1.0)
        tasks = [t for t in (self._pump_task, self._timer_task) if t is not None]
        await asyncio.gather(*tasks, return_exceptions=True)
        if self._proc is not None:
            await self._proc.terminate(1.0)
        self._log.close()
        return self.state

    def _set(self, state: AttemptState) -> None:
        self.state = state
        if self._on_change is not None:
            self._on_change(self)

    def _finish(self, state: AttemptState, error: str | None = None) -> None:
        if self.finished:
            return
        self.state = state
        self.error = error
        self.ended_at = datetime.now(UTC)
        self._done.set()
        if self._on_change is not None:
            self._on_change(self)
