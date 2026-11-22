from __future__ import annotations

import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from cloudripr.library.index import LibraryIndex, classify


def touch(root: Path, rel: str, size: int = 10, mtime: float | None = None) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)
    if mtime is not None:
        os.utime(p, (mtime, mtime))


def test_classify_pairs_live_photos() -> None:
    kinds = classify(
        [
            "2026/10/IMG_1.HEIC",
            "2026/10/IMG_1_HEVC.MOV",
            "2026/10/IMG_2.JPG",
            "2026/10/IMG_2.MOV",
            "2026/10/IMG_3.MOV",
            "2026/10/IMG_4.HEIC",
            "2026/09/IMG_1.HEIC",
        ]
    )
    assert kinds["2026/10/IMG_1.HEIC"] == ("live", "2026/10/IMG_1_HEVC.MOV")
    assert kinds["2026/10/IMG_1_HEVC.MOV"] == ("live_video", "2026/10/IMG_1.HEIC")
    assert kinds["2026/10/IMG_2.JPG"] == ("live", "2026/10/IMG_2.MOV")
    assert kinds["2026/10/IMG_3.MOV"] == ("video", None)
    assert kinds["2026/10/IMG_4.HEIC"] == ("photo", None)
    assert kinds["2026/09/IMG_1.HEIC"] == ("photo", None)  # other folder: no pair


def test_first_scan_skips_hidden_and_non_media(tmp_path: Path) -> None:
    root = tmp_path / "photos"
    for rel in [
        "2026/10/IMG_1.HEIC",
        "2026/10/IMG_1_HEVC.MOV",
        "2026/10/notes.txt",
        ".folderstructure",
        ".hidden/IMG_9.HEIC",
        "2026/10/.IMG_8.HEIC",
    ]:
        touch(root, rel)
    idx = LibraryIndex(tmp_path / "cache" / "library.db")
    assert not idx.has_root(root)
    result = idx.scan(root)
    assert result.added == ["2026/10/IMG_1.HEIC", "2026/10/IMG_1_HEVC.MOV"]
    assert result.removed == []
    assert result.total == 2
    assert idx.has_root(root)
    assert idx.count(root) == 2
    assert idx.kinds(root) == {"2026/10/IMG_1.HEIC": "live", "2026/10/IMG_1_HEVC.MOV": "live_video"}


def test_rescan_diff_and_late_pairing(tmp_path: Path) -> None:
    root = tmp_path / "photos"
    touch(root, "2026/10/IMG_1.HEIC", mtime=1_700_000_000)
    touch(root, "2026/10/IMG_2.HEIC")
    idx = LibraryIndex(tmp_path / "library.db")
    idx.scan(root)
    assert idx.kinds(root)["2026/10/IMG_1.HEIC"] == "photo"
    os.utime(root / "2026/10/IMG_1.HEIC", (1_700_000_500, 1_700_000_500))  # changed, not new
    (root / "2026/10/IMG_2.HEIC").unlink()
    touch(root, "2026/10/IMG_1_HEVC.MOV")
    result = idx.scan(root)
    assert result.added == ["2026/10/IMG_1_HEVC.MOV"]
    assert result.removed == ["2026/10/IMG_2.HEIC"]
    assert idx.kinds(root)["2026/10/IMG_1.HEIC"] == "live"


def test_missing_root_keeps_the_index(tmp_path: Path) -> None:
    root = tmp_path / "photos"
    touch(root, "a.HEIC")
    idx = LibraryIndex(tmp_path / "library.db")
    idx.scan(root)
    (root / "a.HEIC").unlink()
    root.rmdir()
    result = idx.scan(root)
    assert result.removed == []
    assert result.errors != []
    assert idx.count(root) == 1


def test_roots_are_separate_and_persist(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    touch(a, "x.HEIC")
    touch(b, "y.MOV")
    idx = LibraryIndex(tmp_path / "library.db")
    idx.scan(a)
    idx.scan(b)
    idx.close()
    again = LibraryIndex(tmp_path / "library.db")
    assert again.count(a) == 1
    assert again.kinds(b) == {"y.MOV": "video"}


def test_unreadable_subdir_is_not_treated_as_removed(tmp_path: Path) -> None:
    if os.geteuid() == 0:  # noqa: PT009
        pytest.skip("Running as root; permissions don't restrict access")

    root = tmp_path / "photos"
    touch(root, "2026/10/IMG_1.HEIC")
    idx = LibraryIndex(tmp_path / "library.db")
    idx.scan(root)
    assert idx.count(root) == 1

    # Revoke read permissions on the subdirectory
    subdir = root / "2026"
    original_mode = subdir.stat().st_mode
    try:
        subdir.chmod(0o000)
        result = idx.scan(root)
        # Files in unreadable directory are NOT reported as removed
        assert result.removed == []
        # But there should be errors
        assert result.errors != []
        # Index count unchanged
        assert idx.count(root) == 1
    finally:
        # Restore permissions
        subdir.chmod(original_mode)


def test_unpaired_mov_after_photo_deletion(tmp_path: Path) -> None:
    root = tmp_path / "photos"
    touch(root, "2026/10/IMG_1.HEIC")
    touch(root, "2026/10/IMG_1.MOV")
    idx = LibraryIndex(tmp_path / "library.db")
    idx.scan(root)
    # Initially paired as live photo
    assert idx.kinds(root) == {
        "2026/10/IMG_1.HEIC": "live",
        "2026/10/IMG_1.MOV": "live_video",
    }

    # Delete the photo, leaving the video
    (root / "2026/10/IMG_1.HEIC").unlink()
    result = idx.scan(root)
    # Video is now unpaired
    assert result.added == []
    assert result.removed == ["2026/10/IMG_1.HEIC"]
    assert idx.kinds(root) == {"2026/10/IMG_1.MOV": "video"}


def test_root_as_file_is_not_treated_as_empty(tmp_path: Path) -> None:
    root = tmp_path / "photos"
    touch(root, "a.HEIC")
    idx = LibraryIndex(tmp_path / "library.db")
    idx.scan(root)
    assert idx.count(root) == 1

    # Replace the directory with a file
    shutil.rmtree(root)
    root.write_text("not a directory")

    result = idx.scan(root)
    # File should not be reported as removed
    assert result.removed == []
    # There should be an error
    assert result.errors != []
    # Index count unchanged
    assert idx.count(root) == 1


def test_stat_failure_does_not_cause_removal(tmp_path: Path) -> None:
    root = tmp_path / "photos"
    touch(root, "2026/10/IMG_1.HEIC")
    touch(root, "2026/10/IMG_2.HEIC")
    idx = LibraryIndex(tmp_path / "library.db")
    idx.scan(root)
    assert idx.count(root) == 2

    # Monkeypatch os.stat to fail for one file during rescan
    original_stat = os.stat

    def failing_stat(path: str | bytes, *args: object, **kwargs: object) -> object:
        if isinstance(path, (str, bytes)):
            path_str = path if isinstance(path, str) else path.decode()
            if "IMG_1.HEIC" in path_str:
                raise OSError(f"stat failed for {path}")
        return original_stat(path, *args, **kwargs)

    with patch("cloudripr.library.index.os.stat", side_effect=failing_stat):
        result = idx.scan(root)

    # The file with stat failure should not be reported as removed
    assert result.removed == []
    # There should be an error
    assert result.errors != []
    # Index count unchanged (both files still indexed)
    assert idx.count(root) == 2


def test_removing_mov_unpairs_its_photo(tmp_path: Path) -> None:
    root = tmp_path / "photos"
    touch(root, "2026/10/IMG_1.HEIC")
    touch(root, "2026/10/IMG_1.MOV")
    idx = LibraryIndex(tmp_path / "library.db")
    idx.scan(root)
    # Initially paired as live photo
    assert idx.kinds(root) == {
        "2026/10/IMG_1.HEIC": "live",
        "2026/10/IMG_1.MOV": "live_video",
    }

    # Delete the video, leaving the photo
    (root / "2026/10/IMG_1.MOV").unlink()
    result = idx.scan(root)
    # Video removed, photo is now unpaired
    assert result.added == []
    assert result.removed == ["2026/10/IMG_1.MOV"]
    assert idx.kinds(root) == {"2026/10/IMG_1.HEIC": "photo"}


def test_classify_keeps_names_that_differ_only_in_case() -> None:
    # Two different iCloud assets, saved side by side on a case-sensitive disk.
    kinds = classify(["2023/03/A.MP4", "2023/03/A.mp4", "2023/03/B.JPG", "2023/03/b.jpg"])
    assert kinds["2023/03/A.MP4"] == ("video", None)
    assert kinds["2023/03/A.mp4"] == ("video", None)
    assert kinds["2023/03/B.JPG"] == ("photo", None)
    assert kinds["2023/03/b.jpg"] == ("photo", None)


def test_scan_indexes_names_that_differ_only_in_case(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    touch(lib, "2023/03/A.MP4", size=20)
    touch(lib, "2023/03/A.mp4", size=30)
    index = LibraryIndex(tmp_path / "index.db")
    result = index.scan(lib)
    assert sorted(result.added) == ["2023/03/A.MP4", "2023/03/A.mp4"]
