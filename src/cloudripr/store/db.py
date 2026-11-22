"""Durable app state in SQLite: runs, run files, auth attempts, flags."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


FINAL_STATUSES = frozenset(
    {"success", "failed", "stopped", "needs_reauth", "skipped", "gate_blocked"}
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  policy TEXT NOT NULL,
  trigger TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  reason TEXT,
  ended_at TEXT,
  exit_code INTEGER,
  downloaded INTEGER NOT NULL DEFAULT 0,
  filter_kept INTEGER NOT NULL DEFAULT 0,
  filter_deleted INTEGER NOT NULL DEFAULT 0,
  dry_run INTEGER NOT NULL DEFAULT 0,
  would_download INTEGER,
  icloudpd_version TEXT,
  log_path TEXT,
  unreadable INTEGER
);
CREATE INDEX IF NOT EXISTS runs_by_policy ON runs(policy, started_at);
CREATE TABLE IF NOT EXISTS run_files (
  run_id TEXT NOT NULL,
  path TEXT NOT NULL,
  PRIMARY KEY (run_id, path)
);
CREATE TABLE IF NOT EXISTS auth_attempts (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  outcome TEXT,
  log_path TEXT
);
CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class RunRecord:
    id: str
    policy: str
    trigger: str
    status: str
    started_at: datetime
    reason: str | None = None
    ended_at: datetime | None = None
    exit_code: int | None = None
    downloaded: int = 0
    filter_kept: int = 0
    filter_deleted: int = 0
    dry_run: bool = False
    would_download: int | None = None
    icloudpd_version: str | None = None
    log_path: str | None = None
    unreadable: int | None = None  # new files of this run that can't be read (Photos check)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["ended_at"] = self.ended_at.isoformat() if self.ended_at else None
        return data


@dataclass
class AuthAttemptRecord:
    id: str
    started_at: datetime
    ended_at: datetime | None = None
    outcome: str | None = None
    log_path: str | None = None

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["ended_at"] = self.ended_at.isoformat() if self.ended_at else None
        return data


_RUN_COLUMNS = [f.name for f in fields(RunRecord)]
_ATTEMPT_COLUMNS = [f.name for f in fields(AuthAttemptRecord)]


def _to_db(value: Any) -> Any:  # noqa: ANN401
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    return value


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _run_from_row(row: sqlite3.Row) -> RunRecord:
    data = dict(row)
    data["started_at"] = datetime.fromisoformat(data["started_at"])
    data["ended_at"] = _dt(data["ended_at"])
    data["dry_run"] = bool(data["dry_run"])
    return RunRecord(**data)


def _attempt_from_row(row: sqlite3.Row) -> AuthAttemptRecord:
    data = dict(row)
    data["started_at"] = datetime.fromisoformat(data["started_at"])
    data["ended_at"] = _dt(data["ended_at"])
    return AuthAttemptRecord(**data)


class _Result:
    """A query's rows, read while the lock was held."""

    def __init__(self, rows: list[sqlite3.Row], rowcount: int) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def fetchone(self) -> sqlite3.Row | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[sqlite3.Row]:
        return self._rows

    def __iter__(self) -> Iterator[sqlite3.Row]:
        return iter(self._rows)


class _LockedConnection:
    """One SQLite connection shared by the event loop and the API's thread pool.

    sqlite3 objects must not be used from two threads at once, so every call holds
    the lock until its rows are read.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.RLock()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> _Result:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return _Result(cur.fetchall(), cur.rowcount)

    def executemany(self, sql: str, seq: Iterable[Sequence[Any]]) -> _Result:
        with self._lock:
            cur = self._conn.executemany(sql, seq)
            return _Result([], cur.rowcount)

    def executescript(self, script: str) -> None:
        with self._lock:
            self._conn.executescript(script)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class StateDB:
    """State database; safe to use from the event loop and from API worker threads."""

    def __init__(self, path: Path) -> None:
        raw = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        raw.row_factory = sqlite3.Row
        self._conn = _LockedConnection(raw)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(runs)")}
        if "unreadable" not in have:  # added after the first release
            self._conn.execute("ALTER TABLE runs ADD COLUMN unreadable INTEGER")

    def close(self) -> None:
        self._conn.close()

    def _upsert(self, table: str, columns: list[str], values: list[Any]) -> None:
        cols = ",".join(columns)
        marks = ",".join("?" for _ in columns)
        updates = ",".join(f"{c}=excluded.{c}" for c in columns if c != "id")
        self._conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({marks}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            values,
        )

    # ---- runs -------------------------------------------------------------

    def save_run(self, rec: RunRecord) -> None:
        self._upsert("runs", _RUN_COLUMNS, [_to_db(getattr(rec, c)) for c in _RUN_COLUMNS])

    def get_run(self, run_id: str) -> RunRecord | None:
        row = self._conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return _run_from_row(row) if row else None

    def list_runs(self, *, policy: str | None = None, limit: int = 50) -> list[RunRecord]:
        if policy is None:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
            )
        else:
            rows = self._conn.execute(
                "SELECT * FROM runs WHERE policy=? ORDER BY started_at DESC LIMIT ?",
                (policy, limit),
            )
        return [_run_from_row(r) for r in rows]

    def last_run(self, policy: str) -> RunRecord | None:
        runs = self.list_runs(policy=policy, limit=1)
        return runs[0] if runs else None

    def last_success(self, policy: str) -> RunRecord | None:
        """Most recent successful *real* (not dry) run of `policy`."""
        row = self._conn.execute(
            "SELECT * FROM runs WHERE policy=? AND status='success' AND dry_run=0 "
            "ORDER BY started_at DESC LIMIT 1",
            (policy,),
        ).fetchone()
        return _run_from_row(row) if row else None

    def add_run_files(self, run_id: str, paths: Iterable[str]) -> None:
        self._conn.executemany(
            "INSERT OR IGNORE INTO run_files (run_id, path) VALUES (?, ?)",
            [(run_id, p) for p in paths],
        )

    def run_files(self, run_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT path FROM run_files WHERE run_id=? ORDER BY path", (run_id,)
        )
        return [r["path"] for r in rows]

    def prune_runs(self, policy: str, *, keep: int) -> list[RunRecord]:
        """Delete finished runs of `policy` beyond the newest `keep`; return them."""
        rows = self._conn.execute(
            "SELECT * FROM runs WHERE policy=? ORDER BY started_at DESC", (policy,)
        ).fetchall()
        protected = self.last_success(policy)  # the durable "library is known" signal
        doomed = [
            _run_from_row(r)
            for r in rows[keep:]
            if r["status"] in FINAL_STATUSES and (protected is None or r["id"] != protected.id)
        ]
        for rec in doomed:
            self._conn.execute("DELETE FROM run_files WHERE run_id=?", (rec.id,))
            self._conn.execute("DELETE FROM runs WHERE id=?", (rec.id,))
        return doomed

    def mark_unfinished_runs_failed(self, reason: str) -> int:
        cur = self._conn.execute(
            "UPDATE runs SET status='failed', reason=?, ended_at=? "
            "WHERE status IN ('queued','running')",
            (reason, _now().isoformat()),
        )
        return cur.rowcount

    # ---- auth attempts ----------------------------------------------------

    def save_attempt(self, rec: AuthAttemptRecord) -> None:
        self._upsert(
            "auth_attempts", _ATTEMPT_COLUMNS, [_to_db(getattr(rec, c)) for c in _ATTEMPT_COLUMNS]
        )

    def get_attempt(self, attempt_id: str) -> AuthAttemptRecord | None:
        row = self._conn.execute("SELECT * FROM auth_attempts WHERE id=?", (attempt_id,)).fetchone()
        return _attempt_from_row(row) if row else None

    def list_attempts(self, *, limit: int = 20) -> list[AuthAttemptRecord]:
        rows = self._conn.execute(
            "SELECT * FROM auth_attempts ORDER BY started_at DESC LIMIT ?", (limit,)
        )
        return [_attempt_from_row(r) for r in rows]

    def mark_unfinished_attempts(self, outcome: str) -> int:
        cur = self._conn.execute(
            "UPDATE auth_attempts SET outcome=?, ended_at=? WHERE outcome IS NULL",
            (outcome, _now().isoformat()),
        )
        return cur.rowcount

    # ---- key/value --------------------------------------------------------

    def kv_get(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def kv_set(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def kv_delete(self, key: str) -> None:
        self._conn.execute("DELETE FROM kv WHERE key=?", (key,))

    def kv_get_json(self, key: str) -> Any:  # noqa: ANN401
        raw = self.kv_get(key)
        return json.loads(raw) if raw is not None else None

    def kv_set_json(self, key: str, value: Any) -> None:  # noqa: ANN401
        self.kv_set(key, json.dumps(value))
