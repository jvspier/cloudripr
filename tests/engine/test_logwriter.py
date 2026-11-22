from __future__ import annotations

import re
from pathlib import Path

from cloudripr.engine.logwriter import LogWriter


def test_prefixes_timestamp_unless_present(tmp_path: Path) -> None:
    w = LogWriter(tmp_path / "runs" / "r.log")
    w.write("INFO     hello")
    w.write("2026-10-14 03:00:00 INFO     keep")
    w.close()
    lines = (tmp_path / "runs" / "r.log").read_text().splitlines()
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} INFO     hello$", lines[0])
    assert lines[1] == "2026-10-14 03:00:00 INFO     keep"
    assert w.errors == 0


def test_unwritable_path_counts_errors_never_raises(tmp_path: Path) -> None:
    target = tmp_path / "is-a-dir"
    target.mkdir()
    w = LogWriter(target)
    w.write("x")
    w.write("y")
    w.close()
    assert w.errors >= 2


def test_write_after_close_counts_error(tmp_path: Path) -> None:
    w = LogWriter(tmp_path / "r.log")
    w.close()
    w.write("late")
    assert w.errors == 1
