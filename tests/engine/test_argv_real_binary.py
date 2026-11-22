"""Every flag the engine can emit must exist in the installed icloudpd --help."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from cloudripr.engine.argv import base_args, download_args
from cloudripr.store.account_store import Account
from cloudripr.store.models import Policy


_FLAG_RE = re.compile(r"(?:^|[\s,])(--[a-z0-9][a-z0-9-]*)")

REPRESENTATIVE: dict[str, object] = {
    "folder_structure": "{:%Y/%m/%d}",
    "size": ["original", "medium"],
    "live_photo_size": "original",
    "force_size": True,
    "align_raw": "original",
    "keep_unicode_in_filenames": True,
    "set_exif_datetime": True,
    "live_photo_mov_filename_policy": "suffix",
    "file_match_policy": "name-size-dedup-with-suffix",
    "xmp_sidecar": True,
    "use_os_locale": True,
    "album": "Favorites",
    "recent": 10,
    "until_found": 5,
    "skip_videos": True,
    "skip_photos": True,
    "skip_live_photos": True,
    "auto_delete": True,
    "keep_icloud_recent_days": 30,
    "threads_num": 4,
    "skip_created_before": "2020-01-01",
    "skip_created_after": "2024-01-01",
    "delete_after_download": True,
}


@pytest.fixture(scope="module")
def real_flags() -> set[str]:
    exe = shutil.which("icloudpd")
    if exe is None:
        pytest.skip("icloudpd binary not installed")
    out = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=60).stdout
    return set(_FLAG_RE.findall(out))


def test_every_emitted_flag_exists(real_flags: set[str]) -> None:
    policy = Policy(
        name="p",
        username="u@x.com",
        directory="/tmp/p",
        cron="0 3 * * *",
        icloudpd=REPRESENTATIVE,
    )
    argv = [
        *base_args(Account(apple_id="u@x.com", domain="com"), Path("/s")),
        *download_args(policy, library="PrimarySync", dry_run=True),
        "--auth-only",
        "--list-libraries",
        "--notification-script",
    ]
    emitted = {t for t in argv if t.startswith("--")}
    assert emitted - real_flags == set()
