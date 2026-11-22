from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import TextIO


_TS_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s")


class LogWriter:
    """Append-only log. Never raises: a full disk must not kill a run."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.errors = 0
        self._fh: TextIO | None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        except OSError:
            self._fh = None
            self.errors += 1

    def write(self, text: str) -> None:
        if not _TS_PREFIX_RE.match(text):
            text = f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}"
        if self._fh is None:
            self.errors += 1
            return
        try:
            self._fh.write(text + "\n")
        except (OSError, ValueError):
            self.errors += 1

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                self.errors += 1
        self._fh = None
