"""Render thumbnails and previews of library files into /cache.

Reads the original, never writes next to it. A file that can't be decoded raises
MediaError with a short reason the Photos tab shows ("Can't be read: …").
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import pillow_heif
from PIL import Image, ImageOps


pillow_heif.register_heif_opener()

THUMB = (400, 75)  # (longest edge in px, JPEG quality)
PREVIEW = (1600, 82)
_FFMPEG_TIMEOUT = 60
# Decoding a 48 MP photo or a video takes real memory and CPU: a month opened for the
# first time must not start dozens at once on a small server.
MAX_RENDERS = 3
_renders = threading.BoundedSemaphore(MAX_RENDERS)
_NICE = ["nice", "-n", "10"] if shutil.which("nice") else []
# Pillow can't decode most camera RAW files; that isn't a damaged file.
RAW_SUFFIXES = frozenset({".dng", ".raw", ".cr2", ".cr3", ".nef", ".arw"})


class MediaError(Exception):
    """The file can't be turned into an image; str() is the user-facing reason."""


def render(src: Path, dst: Path, *, max_edge: int, quality: int, is_video: bool) -> None:
    """Write a JPEG of `src` (at most `max_edge` px) to `dst`, atomically."""
    try:
        if src.stat().st_size == 0:
            raise MediaError("Can't be read: the file is empty")
    except OSError as exc:
        raise MediaError(f"Can't be read: {exc.strerror or exc}") from exc
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dst.parent, suffix=".tmp.jpg")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with _renders:
            if is_video:
                _video_frame(src, tmp, max_edge)
            else:
                try:
                    _image(src, tmp, max_edge, quality)
                except MediaError:
                    if src.suffix.lower() not in RAW_SUFFIXES:
                        raise
                    _raw_placeholder(tmp, max_edge)
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)


def _raw_placeholder(out: Path, max_edge: int) -> None:
    """A plain tile for a RAW file Pillow can't show; the file itself is fine."""
    Image.new("RGB", (max_edge, max_edge), (90, 88, 110)).save(out, "JPEG", quality=60)


def _image(src: Path, out: Path, max_edge: int, quality: int) -> None:
    try:
        with Image.open(src) as img:
            img.load()
            shown = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as exc:  # Pillow raises many types for broken files
        raise MediaError("Can't be read: the image is damaged or incomplete") from exc
    shown.thumbnail((max_edge, max_edge))
    shown.save(out, "JPEG", quality=quality, optimize=True)


def _video_frame(src: Path, out: Path, max_edge: int) -> None:
    scale = f"scale='min({max_edge},iw)':'min({max_edge},ih)':force_original_aspect_ratio=decrease"
    for seek in ("1", "0"):  # clips shorter than a second have no frame at 1 s
        try:
            subprocess.run(
                [
                    *_NICE, "ffmpeg", "-v", "error", "-y", "-ss", seek, "-i", str(src),
                    "-frames:v", "1", "-vf", scale, "-q:v", "4", "-f", "image2", str(out),
                ],
                check=True,
                capture_output=True,
                timeout=_FFMPEG_TIMEOUT,
            )  # fmt: skip
        except FileNotFoundError as exc:
            raise MediaError("Can't make a video thumbnail: ffmpeg is missing") from exc
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
        if out.stat().st_size > 0:
            return
    raise MediaError("Can't be read: the video is damaged or incomplete")


def video_duration(src: Path) -> float | None:
    """Length in seconds according to ffprobe, or None when unknown."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(src),
            ],
            capture_output=True,
            text=True,
            timeout=_FFMPEG_TIMEOUT,
        )  # fmt: skip
        return float(result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
