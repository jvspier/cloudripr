from __future__ import annotations

import os
from pathlib import Path


def write_atomic(path: Path, data: bytes, *, mode: int = 0o644) -> None:
    """Write via temp file + fsync + rename so readers never see a half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
