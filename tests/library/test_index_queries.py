from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from cloudripr.library.index import LibraryIndex


NOV = datetime(2026, 11, 15, 12).timestamp()
OCT = datetime(2026, 10, 15, 12).timestamp()


def put(root: Path, rel: str, mtime: float, size: int = 10) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)
    os.utime(p, (mtime, mtime))
    return p


def indexed(tmp_path: Path) -> tuple[LibraryIndex, Path]:
    root = tmp_path / "lib"
    put(root, "2026/11/IMG_1.HEIC", NOV)
    put(root, "2026/11/IMG_1_HEVC.MOV", NOV)
    put(root, "2026/11/CLIP.MP4", NOV + 60)
    put(root, "2026/10/IMG_2.JPG", OCT)
    index = LibraryIndex(tmp_path / "library.db")
    index.scan(root)
    return index, root


def test_old_index_gains_columns(tmp_path: Path) -> None:
    db = tmp_path / "library.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE items (id INTEGER PRIMARY KEY, root TEXT NOT NULL, rel TEXT NOT NULL,"
        " size INTEGER NOT NULL, mtime REAL NOT NULL, kind TEXT NOT NULL, pair_rel TEXT,"
        " UNIQUE (root, rel));"
        "CREATE TABLE roots (root TEXT PRIMARY KEY, scanned_at TEXT NOT NULL);"
        "INSERT INTO items (root, rel, size, mtime, kind) VALUES ('/r', 'a.JPG', 1, 0, 'photo');"
    )
    conn.commit()
    conn.close()
    index = LibraryIndex(db)
    item = index.get(1)
    assert item is not None
    assert item.problem is None
    assert item.duration is None


def test_summary_counts_live_once(tmp_path: Path) -> None:
    index, _ = indexed(tmp_path)
    summary = index.summary()
    assert summary["total"] == 3  # live pair + clip + jpg
    assert summary["unreadable"] == 0
    assert summary["scanned_at"] is not None


def test_months_newest_first_with_unreadable(tmp_path: Path) -> None:
    index, _ = indexed(tmp_path)
    clip = next(i for i in index.items_in_month("2026-11") if i.rel.endswith("CLIP.MP4"))
    index.set_problem(clip.id, "Can't be read: the video is damaged or incomplete")
    assert index.months() == [
        {"month": "2026-11", "count": 2, "unreadable": 1},
        {"month": "2026-10", "count": 1, "unreadable": 0},
    ]
    assert index.summary()["unreadable"] == 1


def test_items_in_month_newest_first_without_live_video(tmp_path: Path) -> None:
    index, _ = indexed(tmp_path)
    rels = [i.rel for i in index.items_in_month("2026-11")]
    assert rels == ["2026/11/CLIP.MP4", "2026/11/IMG_1.HEIC"]


def test_items_for_paths_matches_absolute_paths(tmp_path: Path) -> None:
    index, root = indexed(tmp_path)
    items = index.items_for_paths(
        [str(root / "2026/10/IMG_2.JPG"), str(root / "2026/11/IMG_1_HEVC.MOV"), "/elsewhere/x.JPG"]
    )
    assert [i.rel for i in items] == ["2026/10/IMG_2.JPG"]  # a Live Photo's video counts once


def test_rescan_keeps_problem_for_unchanged_file(tmp_path: Path) -> None:
    index, root = indexed(tmp_path)
    item = index.items_in_month("2026-10")[0]
    index.set_problem(item.id, "broken")
    index.set_duration(item.id, 3.5)
    index.scan(root)
    again = index.get(item.id)
    assert again is not None
    assert again.problem == "broken"
    assert again.duration == 3.5


def test_changed_file_clears_problem(tmp_path: Path) -> None:
    index, root = indexed(tmp_path)
    item = index.items_in_month("2026-10")[0]
    index.set_problem(item.id, "broken")
    put(root, "2026/10/IMG_2.JPG", OCT, size=99)  # re-downloaded
    index.scan(root)
    again = index.get(item.id)
    assert again is not None
    assert again.problem is None
    assert again.size == 99


def test_items_for_paths_counts_a_live_photo_once(tmp_path: Path) -> None:
    index, root = indexed(tmp_path)
    items = index.items_for_paths(
        [str(root / "2026/11/IMG_1.HEIC"), str(root / "2026/11/IMG_1_HEVC.MOV")]
    )
    assert [i.rel for i in items] == ["2026/11/IMG_1.HEIC"]
