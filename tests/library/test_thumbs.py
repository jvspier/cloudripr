from __future__ import annotations

from pathlib import Path

from PIL import Image

from cloudripr.library.index import LibraryIndex
from cloudripr.library.thumbs import Thumbs


def setup(tmp_path: Path) -> tuple[LibraryIndex, Thumbs, Path]:
    root = tmp_path / "lib"
    (root / "2026/11").mkdir(parents=True)
    Image.new("RGB", (900, 600), (1, 2, 3)).save(root / "2026/11/GOOD.JPG")
    (root / "2026/11/BAD.JPG").write_bytes(b"\xff\xd8\xff" + b"\0" * 50)
    index = LibraryIndex(tmp_path / "cache/library.db")
    index.scan(root)
    return index, Thumbs(index, tmp_path / "cache"), root


def by_name(index: LibraryIndex, name: str):  # noqa: ANN201
    return next(i for i in index.items_in_month("2026-11") if i.rel.endswith(name))


def test_ensure_caches_and_reuses(tmp_path: Path) -> None:
    index, thumbs, _ = setup(tmp_path)
    good = by_name(index, "GOOD.JPG")
    first = thumbs.ensure(good)
    assert first is not None
    assert first == thumbs.thumb_path(good)
    assert first.is_relative_to(tmp_path / "cache" / "thumbs")
    stamp = first.stat().st_mtime_ns
    assert thumbs.ensure(good) == first
    assert first.stat().st_mtime_ns == stamp
    preview = thumbs.ensure(good, preview=True)
    assert preview is not None
    with Image.open(preview) as img:
        assert max(img.size) == 900  # never upscaled past the original


def test_unreadable_sets_problem_then_clears_after_fix(tmp_path: Path) -> None:
    index, thumbs, root = setup(tmp_path)
    bad = by_name(index, "BAD.JPG")
    assert thumbs.ensure(bad) is None
    marked = index.get(bad.id)
    assert marked is not None
    assert marked.problem is not None
    assert marked.problem.startswith("Can't be read")
    Image.new("RGB", (50, 50)).save(root / "2026/11/BAD.JPG")  # fixed on disk, same row
    assert thumbs.ensure(marked) is not None
    fixed = index.get(bad.id)
    assert fixed is not None
    assert fixed.problem is None


def test_check_counts_problems(tmp_path: Path) -> None:
    index, thumbs, _ = setup(tmp_path)
    assert thumbs.check(index.items_in_month("2026-11")) == 1
