"""Build a demo cloudripr installation for README screenshots.

    uv run python scripts/screenshots/seed.py OUT_DIR

Creates OUT_DIR/library (generated landscape "photos", a few short videos and one damaged
file) and OUT_DIR/data (a signed-in account, one policy, a week of nightly runs). Nothing
here talks to Apple. Dates are relative to now, so the screenshots always look fresh.
"""

from __future__ import annotations

import colorsys
import math
import os
import random
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from cloudripr.account.service import STATE_KEY
from cloudripr.auth import Authenticator
from cloudripr.library.index import LibraryIndex
from cloudripr.library.thumbs import Thumbs
from cloudripr.migration import MIGRATED_KEY, NAMING_FROZEN_KEY
from cloudripr.paths import DataPaths
from cloudripr.runs.service import ICLOUD_TOTAL_KEY
from cloudripr.store.account_store import Account, AccountStore
from cloudripr.store.db import RunRecord, StateDB
from cloudripr.store.models import Policy
from cloudripr.store.policy_store import PolicyStore


PASSWORD = "demo-password"
POLICY = "icloud"


def landscape(path: Path, rng: random.Random, size: tuple[int, int]) -> None:
    """A stylised landscape: sky gradient, sun, layered hills."""
    w, h = size
    hue = rng.random()
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        r, g, b = colorsys.hsv_to_rgb((hue + 0.08 * t) % 1, 0.25 + 0.35 * t, 1 - 0.15 * t)
        draw.line([(0, y), (w, y)], fill=(int(r * 255), int(g * 255), int(b * 255)))
    sun = rng.randint(w // 10, w // 6)
    sx, sy = rng.randint(sun, w - sun), rng.randint(h // 8, h // 2)
    draw.ellipse([sx - sun, sy - sun, sx + sun, sy + sun], fill=(255, 244, 214))
    layers = rng.randint(3, 4)
    for i in range(layers):
        base = h * (0.5 + 0.13 * i)
        amp = h * rng.uniform(0.04, 0.1)
        freq = rng.uniform(1.2, 3.0)
        phase = rng.uniform(0, math.tau)
        dark = 0.75 - 0.17 * i
        r, g, b = colorsys.hsv_to_rgb((hue + 0.35) % 1, 0.45, dark)
        pts = [
            (x, base + amp * math.sin(freq * x / w * math.tau + phase)) for x in range(0, w + 8, 8)
        ]
        draw.polygon([(0, h), *pts, (w, h)], fill=(int(r * 255), int(g * 255), int(b * 255)))
    img.filter(ImageFilter.GaussianBlur(1.2)).save(path, "JPEG", quality=88)


def video(path: Path, still: Path, seconds: int) -> None:
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(still), "-t", str(seconds),
            "-vf", "scale=960:-2,zoompan=z='1+0.002*on':d=1:s=960x720", "-r", "15",
            "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
    )  # fmt: skip


def main(out: Path) -> None:  # noqa: C901, PLR0915
    if out.exists():
        shutil.rmtree(out)
    library = out / "library"
    rng = random.Random(7)
    now = datetime.now().astimezone().replace(second=0, microsecond=0)

    # ---- library: ~4 months, newest month busiest -------------------------------------
    files_by_day: dict[datetime, list[Path]] = {}
    counter = 4000
    for months_back, count in ((0, 46), (1, 38), (2, 30), (3, 24)):
        month_start = (now.replace(day=1) - timedelta(days=31 * months_back)).replace(day=1)
        for _ in range(count):
            day = month_start + timedelta(days=rng.randint(0, 27), hours=rng.randint(8, 20))
            if day > now - timedelta(hours=8):
                day = now - timedelta(days=rng.randint(1, 6), hours=rng.randint(1, 10))
            folder = library / f"{day:%Y}" / f"{day:%m}"
            folder.mkdir(parents=True, exist_ok=True)
            counter += 1
            path = folder / f"IMG_{counter}.JPG"
            landscape(path, rng, rng.choice([(1600, 1200), (1200, 1600), (1500, 1500)]))
            if rng.random() < 0.08 and shutil.which("ffmpeg"):
                clip = path.with_suffix(".MOV")
                video(clip, path, rng.choice([4, 7, 12]))
                os.utime(clip, (day.timestamp(), day.timestamp()))
                files_by_day.setdefault(day, []).append(clip)
                path.unlink()
            else:
                os.utime(path, (day.timestamp(), day.timestamp()))
                files_by_day.setdefault(day, []).append(path)
    # The last week is busiest, so every nightly run brings in a full row of photos.
    for _ in range(48):
        day = now - timedelta(days=rng.randint(0, 6), hours=rng.randint(9, 20))
        folder = library / f"{day:%Y}" / f"{day:%m}"
        folder.mkdir(parents=True, exist_ok=True)
        counter += 1
        path = folder / f"IMG_{counter}.JPG"
        landscape(path, rng, rng.choice([(1600, 1200), (1200, 1600), (1500, 1500)]))
        os.utime(path, (day.timestamp(), day.timestamp()))
        files_by_day.setdefault(day, []).append(path)
    # One interrupted download, three months back, to show the ⚠ check.
    old = sorted(files_by_day)[2]
    broken = old.strftime(f"{library}/%Y/%m/IMG_3999.HEIC")
    Path(broken).write_bytes(b"\0" * 512)
    os.utime(broken, (old.timestamp(), old.timestamp()))
    (library / ".folderstructure").write_text("{:%Y/%m}")

    # ---- data dir -------------------------------------------------------------------
    paths = DataPaths(out / "data", out / "data" / "cache")
    paths.ensure()
    (paths.app / "login.hash").write_text(Authenticator.hash(PASSWORD))
    (paths.session / "demo").write_text("demo session")

    accounts = AccountStore(paths.account)
    accounts.save(Account(apple_id="you@icloud.com", domain="com"))
    accounts.set_password("not-a-real-password")

    policies = PolicyStore(paths.policies)
    policies.load()
    policies.put(
        Policy(
            name=POLICY,
            username="you@icloud.com",
            directory=library,
            cron="0 3 * * *",
            library_kind="personal",
            icloudpd={"folder_structure": "{:%Y/%m}", "size": ["original"]},
        )  # type: ignore[arg-type]
    )

    db = StateDB(paths.state_db)
    db.kv_set(MIGRATED_KEY, "1")
    db.kv_set(NAMING_FROZEN_KEY.format(policy=POLICY), now.isoformat())
    verified = (now - timedelta(hours=2)).astimezone(UTC)
    db.kv_set_json(
        STATE_KEY,
        {"state": "ok", "since": None, "last_verified_at": verified.isoformat(), "reason": None},
    )
    index = LibraryIndex(paths.library_db)
    index.scan(library)
    icloud_total = index.summary()["total"] + 2  # tonight's two newest aren't down yet
    db.kv_set_json(
        ICLOUD_TOTAL_KEY.format(policy=POLICY),
        {"count": icloud_total, "seen_at": now.replace(hour=3).astimezone(UTC).isoformat()},
    )

    # A week of nightly runs; each picks up the photos taken since the night before.
    runs_dir = paths.runs / POLICY
    runs_dir.mkdir(parents=True, exist_ok=True)
    thumbs = Thumbs(index, paths.cache)
    for nights_back in range(7, 0, -1):
        start = (now - timedelta(days=nights_back - 1)).replace(hour=3, minute=0)
        if start > now:
            continue
        since = start - timedelta(days=1)
        new = sorted(p for d, ps in files_by_day.items() if since <= d < start for p in ps)
        run_id = f"{POLICY}-{start:%Y%m%dT%H%M%S}-demo"
        log = runs_dir / f"{run_id}.log"
        lines = [
            f"{start:%Y-%m-%d %H:%M:%S} INFO     Processing user: you@icloud.com",
            f"{start:%Y-%m-%d %H:%M:%S} INFO     Downloading {icloud_total} original photos "
            f"and videos to {library} ...",
            *[f"{start:%Y-%m-%d %H:%M:%S} INFO     Downloaded {p}" for p in new],
            f"{start:%Y-%m-%d %H:%M:%S} INFO     All photos and videos have been downloaded",
        ]
        log.write_text("\n".join(lines) + "\n")
        db.save_run(
            RunRecord(
                id=run_id,
                policy=POLICY,
                trigger="schedule",
                status="success",
                started_at=start.astimezone(UTC),
                ended_at=(start + timedelta(minutes=4 + len(new) // 3)).astimezone(UTC),
                exit_code=0,
                downloaded=len(new),
                icloudpd_version="1.34.0",
                log_path=str(log),
                unreadable=0,
            )
        )
        db.add_run_files(run_id, [str(p) for p in new])
        thumbs.check(index.items_for_paths([str(p) for p in new]))
    print(f"demo ready in {out} (login password: {PASSWORD})")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
