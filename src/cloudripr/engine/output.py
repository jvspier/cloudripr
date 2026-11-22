"""Turn icloudpd's raw stdout/stderr into events.

icloudpd's prompts end in ': ' with no newline (Python's input()), so a
line reader never sees them. We keep the unterminated tail and test it
against the known prompts on every feed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


EventKind = Literal[
    "line",
    "prompt",
    "twofa_required",
    "phone_option",
    "downloaded",
    "would_download",
    "mfa_rejected",
    "bad_password",
    "auth_ok",
    "total",
]


@dataclass(frozen=True)
class OutputEvent:
    kind: EventKind
    text: str
    value: str | None = None


TWOFA_RE = re.compile(r"Two-(?:factor|step) authentication is required")
PHONE_RE = re.compile(r"^\s{2}([a-z]):\s+(\S.*?)\s*$")
DOWNLOADED_RE = re.compile(r"INFO\s+Downloaded\s+(.+?)\s*$")
WOULD_DOWNLOAD_RE = re.compile(r"\[DRY RUN\] Would download\s+(.+?)\s*$")
MFA_REJECTED_RE = re.compile(
    r"Failed to verify two-(?:factor|step) authentication code|Code verification failed"
)
BAD_PASSWORD_RE = re.compile(r"Invalid email/password combination")
TOTAL_RE = re.compile(r"Downloading (\d+) \w+ photos and videos")
AUTH_OK_RE = re.compile(r"Great, you're all set up|Authentication completed successfully")

PROMPTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "code_or_index",
        re.compile(
            r"Please enter two-factor authentication code or device index "
            r"\([a-z](?:\.\.[a-z])?\) to send SMS with a code: $"
        ),
    ),
    (
        "sms_code",
        re.compile(r"Please enter two-factor authentication code that you received over SMS: $"),
    ),
    ("code", re.compile(r"Please enter two-(?:factor|step) authentication code: $")),
)


def _classify(line: str) -> list[OutputEvent]:
    events = [OutputEvent("line", line)]
    if TWOFA_RE.search(line):
        events.append(OutputEvent("twofa_required", line))
    if m := PHONE_RE.match(line):
        events.append(OutputEvent("phone_option", m.group(2), m.group(1)))
    if m := DOWNLOADED_RE.search(line):
        events.append(OutputEvent("downloaded", line, m.group(1)))
    if m := WOULD_DOWNLOAD_RE.search(line):
        events.append(OutputEvent("would_download", line, m.group(1)))
    if MFA_REJECTED_RE.search(line):
        events.append(OutputEvent("mfa_rejected", line))
    if BAD_PASSWORD_RE.search(line):
        events.append(OutputEvent("bad_password", line))
    if m := TOTAL_RE.search(line):
        events.append(OutputEvent("total", line, m.group(1)))
    if AUTH_OK_RE.search(line):
        events.append(OutputEvent("auth_ok", line))
    return events


class OutputParser:
    def __init__(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> list[OutputEvent]:
        self._buf += chunk
        events: list[OutputEvent] = []
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            events.extend(_classify(line.rstrip("\r")))
        for name, pattern in PROMPTS:
            if pattern.search(self._buf):
                prompt = self._buf.rstrip()
                self._buf = ""
                events.append(OutputEvent("line", prompt))
                events.append(OutputEvent("prompt", prompt, name))
                break
        return events

    def flush(self) -> list[OutputEvent]:
        if not self._buf:
            return []
        line, self._buf = self._buf, ""
        return _classify(line.rstrip("\r"))
