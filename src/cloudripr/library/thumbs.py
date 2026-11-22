"""Cached thumbnails and previews for index items, and the unreadable-file check.

Files live in /cache (disposable). A file that can't be rendered is marked with a
problem in the index; a later successful render clears it.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path, PurePosixPath

from cloudripr.library.index import VIDEO_SUFFIXES, Item, LibraryIndex
from cloudripr.library.media import PREVIEW, THUMB, MediaError, render, video_duration


log = logging.getLogger(__name__)


class Thumbs:
    def __init__(self, index: LibraryIndex, cache: Path) -> None:
        self._index = index
        self._cache = cache

    def _path(self, kind: str, item: Item) -> Path:
        root_key = hashlib.sha1(item.root.encode()).hexdigest()[:12]  # noqa: S324 - a name, not security
        return self._cache / kind / root_key / f"{item.rel}.jpg"

    def thumb_path(self, item: Item) -> Path:
        return self._path("thumbs", item)

    def preview_path(self, item: Item) -> Path:
        return self._path("previews", item)

    def ensure(self, item: Item, *, preview: bool = False) -> Path | None:
        """The cached JPEG for `item`, rendered if missing; None if the file can't be read."""
        dst = self.preview_path(item) if preview else self.thumb_path(item)
        if dst.exists():
            return dst
        src = Path(item.root) / item.rel
        is_video = PurePosixPath(item.rel).suffix.lower() in VIDEO_SUFFIXES
        max_edge, quality = PREVIEW if preview else THUMB
        try:
            render(src, dst, max_edge=max_edge, quality=quality, is_video=is_video)
        except MediaError as exc:
            self._index.set_problem(item.id, str(exc))
            return None
        if item.problem is not None:
            self._index.set_problem(item.id, None)
        if is_video and item.duration is None:
            self._index.set_duration(item.id, video_duration(src))
        return dst

    def check(self, items: list[Item]) -> int:
        """Render thumbnails for `items`; return how many can't be read."""
        problems = 0
        for item in items:
            try:
                if self.ensure(item) is None:
                    problems += 1
            except OSError:
                log.exception("thumbnail for %s failed", item.rel)
                problems += 1
        return problems
