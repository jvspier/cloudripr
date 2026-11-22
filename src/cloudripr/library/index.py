"""Read-only index of media files under each policy directory.

Lives in /cache: deleting it is safe, it is rebuilt by the next scan. The
scanner only stats files; it never opens, moves or deletes anything.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any


PHOTO_SUFFIXES = frozenset(
    {
        ".heic",
        ".heif",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".tif",
        ".tiff",
        ".dng",
        ".raw",
        ".cr2",
        ".cr3",
        ".nef",
        ".arw",
    }
)
VIDEO_SUFFIXES = frozenset({".mov", ".mp4", ".m4v", ".avi", ".3gp"})
_MEDIA = PHOTO_SUFFIXES | VIDEO_SUFFIXES

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY,
  root TEXT NOT NULL,
  rel TEXT NOT NULL,
  size INTEGER NOT NULL,
  mtime REAL NOT NULL,
  kind TEXT NOT NULL,
  pair_rel TEXT,
  UNIQUE (root, rel)
);
CREATE INDEX IF NOT EXISTS items_by_time ON items(root, mtime);
CREATE TABLE IF NOT EXISTS roots (
  root TEXT PRIMARY KEY,
  scanned_at TEXT NOT NULL
);
"""


# Columns added after the first release; added to existing databases on open.
_ADDED_COLUMNS = {"problem": "TEXT", "duration": "REAL"}
_LIVE_VIDEO = "live_video"


@dataclass(frozen=True)
class Item:
    id: int
    root: str
    rel: str
    size: int
    taken_at: float  # mtime: icloudpd sets it to the asset's creation date
    kind: str
    pair_rel: str | None
    problem: str | None  # why the file can't be read, if it can't
    duration: float | None  # seconds, videos only, once known


def _item(row: sqlite3.Row) -> Item:
    return Item(
        id=row["id"],
        root=row["root"],
        rel=row["rel"],
        size=row["size"],
        taken_at=row["mtime"],
        kind=row["kind"],
        pair_rel=row["pair_rel"],
        problem=row["problem"],
        duration=row["duration"],
    )


@dataclass(frozen=True)
class ScanResult:
    added: list[str]
    removed: list[str]
    total: int
    errors: list[str] = field(default_factory=list)


def _walk(root: Path) -> tuple[dict[str, tuple[int, float]], list[str]]:
    """Walk media files, collecting errors. Returns (files_dict, errors_list)."""
    files: dict[str, tuple[int, float]] = {}
    errors: list[str] = []

    def onerror(err: OSError) -> None:
        # Extract path from exception if available
        path = getattr(err, "filename", None)
        if path:
            try:
                rel = os.path.relpath(path, root)
                errors.append(rel)
            except ValueError:
                # If we can't make it relative, just use the path
                errors.append(str(path))
        else:
            errors.append(str(err))

    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.startswith(".") or os.path.splitext(name)[1].lower() not in _MEDIA:
                continue
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except OSError:
                try:
                    rel = os.path.relpath(full, root)
                    errors.append(rel)
                except ValueError:
                    errors.append(str(full))
                continue
            rel = PurePosixPath(Path(os.path.relpath(full, root))).as_posix()
            files[rel] = (st.st_size, st.st_mtime)

    return files, errors


def _folder(rel: str) -> str:
    return str(PurePosixPath(rel).parent)


def classify(rels: Iterable[str]) -> dict[str, tuple[str, str | None]]:
    """photo / video / live (photo with its video) / live_video (that video, hidden)."""
    by_dir: dict[str, list[str]] = defaultdict(list)
    for rel in sorted(rels):
        by_dir[_folder(rel)].append(rel)
    result: dict[str, tuple[str, str | None]] = {}
    for dir_rels in by_dir.values():
        # Lower-cased names are only for finding a photo's video: a case-sensitive
        # disk can hold A.MP4 and A.mp4 as two different assets, and both are kept.
        names: dict[str, str] = {}
        for rel in dir_rels:
            names.setdefault(PurePosixPath(rel).name.lower(), rel)
        for rel in dir_rels:
            lower = PurePosixPath(rel).name.lower()
            suffix = os.path.splitext(lower)[1]
            if suffix not in PHOTO_SUFFIXES:
                continue
            stem = lower[: -len(suffix)]
            video = names.get(f"{stem}_hevc.mov") or names.get(f"{stem}.mov")
            if video is not None:
                result[rel] = ("live", video)
                result[video] = ("live_video", rel)
            else:
                result.setdefault(rel, ("photo", None))
        for rel in dir_rels:
            result.setdefault(rel, ("video", None))
    return result


class LibraryIndex:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(items)")}
        for column, sql_type in _ADDED_COLUMNS.items():
            if column not in have:
                self._conn.execute(f"ALTER TABLE items ADD COLUMN {column} {sql_type}")
        self._conn.commit()
        self._lock = threading.Lock()

    def close(self) -> None:
        self._conn.close()

    def has_root(self, root: Path) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT 1 FROM roots WHERE root=?", (str(root),)).fetchone()
        return row is not None

    def count(self, root: Path) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM items WHERE root=?", (str(root),)
            ).fetchone()
        return int(row["n"])

    def kinds(self, root: Path) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute("SELECT rel, kind FROM items WHERE root=?", (str(root),))
            return {r["rel"]: r["kind"] for r in rows}

    def scan(self, root: Path) -> ScanResult:
        key = str(root)
        errors: list[str] = []

        # Check if root is a directory; record error if not
        if not root.is_dir():
            errors.append(".")
            current = {}
        else:
            current, walk_errors = _walk(root)
            errors.extend(walk_errors)

        with self._lock, self._conn:
            existing = {
                r["rel"]: (r["size"], r["mtime"])
                for r in self._conn.execute(
                    "SELECT rel, size, mtime FROM items WHERE root=?", (key,)
                )
            }

            added = sorted(set(current) - set(existing))
            changed = [r for r in set(current) & set(existing) if current[r] != existing[r]]

            # If there are errors, don't report removals and keep the index
            if errors:
                removed = []
                # Only recompute pairing for newly added files
                touched = {_folder(r) for r in added}
                kinds = classify(r for r in current if _folder(r) in touched)
            else:
                removed = sorted(set(existing) - set(current))
                touched = {_folder(r) for r in (*added, *removed)}
                kinds = classify(r for r in current if _folder(r) in touched)

            # Insert new files and update changed ones
            self._conn.executemany(
                "DELETE FROM items WHERE root=? AND rel=?", [(key, r) for r in removed]
            )
            self._conn.executemany(
                "INSERT INTO items (root, rel, size, mtime, kind, pair_rel) VALUES (?,?,?,?,?,?)",
                [(key, r, *current[r], *kinds[r]) for r in added],
            )
            self._conn.executemany(
                "UPDATE items SET size=?, mtime=?, problem=NULL, duration=NULL "
                "WHERE root=? AND rel=?",
                [(*current[r], key, r) for r in changed],
            )
            # Only update kinds for existing rows when there are no errors
            if not errors:
                added_set = set(added)
                self._conn.executemany(
                    "UPDATE items SET kind=?, pair_rel=? WHERE root=? AND rel=?",
                    [(k, pair, key, r) for r, (k, pair) in kinds.items() if r not in added_set],
                )
            # Only update scanned_at if there were no errors
            if not errors:
                self._conn.execute(
                    "INSERT INTO roots (root, scanned_at) VALUES (?, ?) "
                    "ON CONFLICT(root) DO UPDATE SET scanned_at=excluded.scanned_at",
                    (key, datetime.now(UTC).isoformat()),
                )
        return ScanResult(added, removed, len(current), errors)

    # ---- Photos tab queries -------------------------------------------------

    def summary(self) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS total, COUNT(problem) AS unreadable FROM items WHERE kind!=?",
                (_LIVE_VIDEO,),
            ).fetchone()
            scanned = self._conn.execute("SELECT MAX(scanned_at) AS at FROM roots").fetchone()
        return {
            "total": int(row["total"]),
            "unreadable": int(row["unreadable"]),
            "scanned_at": scanned["at"],
        }

    def months(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT strftime('%Y-%m', mtime, 'unixepoch', 'localtime') AS month, "
                "COUNT(*) AS count, COUNT(problem) AS unreadable "
                "FROM items WHERE kind!=? GROUP BY month ORDER BY month DESC",
                (_LIVE_VIDEO,),
            ).fetchall()
        return [dict(r) for r in rows]

    def items_in_month(self, month: str) -> list[Item]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM items WHERE kind!=? "
                "AND strftime('%Y-%m', mtime, 'unixepoch', 'localtime')=? "
                "ORDER BY mtime DESC, rel",
                (_LIVE_VIDEO, month),
            ).fetchall()
        return [_item(r) for r in rows]

    def items_for_paths(self, paths: list[str]) -> list[Item]:
        """Items for absolute file paths (as stored per run), newest first.

        A Live Photo's video is left out: the pair shows (and counts) as one photo.
        """
        with self._lock:
            roots = [r["root"] for r in self._conn.execute("SELECT DISTINCT root FROM items")]
            found: list[Item] = []
            for path in paths:
                for root in roots:
                    prefix = root.rstrip("/") + "/"
                    if path.startswith(prefix):
                        row = self._conn.execute(
                            "SELECT * FROM items WHERE root=? AND rel=?",
                            (root, path[len(prefix) :]),
                        ).fetchone()
                        if row is not None and row["kind"] != _LIVE_VIDEO:
                            found.append(_item(row))
                        break
        return sorted(found, key=lambda i: (-i.taken_at, i.rel))

    def get(self, item_id: int) -> Item | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        return _item(row) if row else None

    def set_problem(self, item_id: int, problem: str | None) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE items SET problem=? WHERE id=?", (problem, item_id))

    def set_duration(self, item_id: int, seconds: float | None) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE items SET duration=? WHERE id=?", (seconds, item_id))
