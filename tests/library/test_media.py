from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from cloudripr.library.media import THUMB, MediaError, render, video_duration


needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _jpeg(path: Path, size: tuple[int, int] = (800, 400), orientation: int | None = None) -> Path:
    img = Image.new("RGB", size, (200, 30, 30))
    exif = Image.Exif()
    if orientation is not None:
        exif[0x0112] = orientation
    img.save(path, "JPEG", exif=exif)
    return path


def _mp4(path: Path, seconds: int = 2) -> Path:
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
            f"testsrc=duration={seconds}:size=640x360:rate=10", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
    )  # fmt: skip
    return path


def test_jpeg_thumb_fits_and_is_rotated(tmp_path: Path) -> None:
    src = _jpeg(tmp_path / "a.JPG", orientation=6)  # rotate 90°: 800x400 shows as 400x800
    dst = tmp_path / "out" / "a.jpg"
    render(src, dst, max_edge=THUMB[0], quality=THUMB[1], is_video=False)
    with Image.open(dst) as out:
        assert out.format == "JPEG"
        assert out.size == (200, 400)


def test_heic_thumb(tmp_path: Path) -> None:
    import pillow_heif

    src = tmp_path / "b.HEIC"
    pillow_heif.from_pillow(Image.new("RGB", (1200, 900), (10, 120, 200))).save(src)
    dst = tmp_path / "b.jpg"
    render(src, dst, max_edge=400, quality=75, is_video=False)
    with Image.open(dst) as out:
        assert out.format == "JPEG"
        assert max(out.size) == 400


@needs_ffmpeg
def test_video_thumb_and_duration(tmp_path: Path) -> None:
    src = _mp4(tmp_path / "c.MP4")
    dst = tmp_path / "c.jpg"
    render(src, dst, max_edge=400, quality=75, is_video=True)
    with Image.open(dst) as out:
        assert out.format == "JPEG"
        assert max(out.size) <= 400
    duration = video_duration(src)
    assert duration is not None
    assert abs(duration - 2.0) < 0.2


def test_truncated_jpeg_raises(tmp_path: Path) -> None:
    full = _jpeg(tmp_path / "full.jpg").read_bytes()
    src = tmp_path / "cut.JPG"
    src.write_bytes(full[:100])
    dst = tmp_path / "cut.jpg"
    with pytest.raises(MediaError):
        render(src, dst, max_edge=400, quality=75, is_video=False)
    assert not dst.exists()


def test_empty_file_raises(tmp_path: Path) -> None:
    src = tmp_path / "empty.HEIC"
    src.write_bytes(b"")
    with pytest.raises(MediaError, match="empty"):
        render(src, tmp_path / "e.jpg", max_edge=400, quality=75, is_video=False)


@needs_ffmpeg
def test_broken_video_raises(tmp_path: Path) -> None:
    src = tmp_path / "bad.MOV"
    src.write_bytes(b"\0" * 64)
    dst = tmp_path / "bad.jpg"
    with pytest.raises(MediaError):
        render(src, dst, max_edge=400, quality=75, is_video=True)
    assert not dst.exists()


def test_undecodable_raw_gets_a_placeholder_not_an_error(tmp_path: Path) -> None:
    src = tmp_path / "IMG_1.DNG"
    src.write_bytes(b"II*\0" + b"\x01" * 4000)  # TIFF-like header Pillow can't render
    dst = tmp_path / "raw.jpg"
    render(src, dst, max_edge=400, quality=75, is_video=False)
    with Image.open(dst) as out:
        assert out.format == "JPEG"


def test_renders_are_limited_to_a_few_at_once(tmp_path: Path) -> None:
    import threading
    import time

    from cloudripr.library import media

    active = 0
    peak = 0
    lock = threading.Lock()
    real = media._image

    def slow(src: Path, out: Path, max_edge: int, quality: int) -> None:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        real(src, out, max_edge, quality)
        with lock:
            active -= 1

    src = _jpeg(tmp_path / "a.JPG")
    media._image = slow  # type: ignore[assignment]
    try:
        threads = [
            threading.Thread(
                target=render,
                args=(src, tmp_path / f"o{i}.jpg"),
                kwargs={"max_edge": 100, "quality": 70, "is_video": False},
            )
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        media._image = real  # type: ignore[assignment]
    assert peak <= media.MAX_RENDERS
