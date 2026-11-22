#!/usr/bin/env python3
"""Simulates upstream icloudpd 1.32.3–1.34.0 closely enough for engine tests.

Prompts, the phone list and log messages are copied from upstream v1.32.3
(verified unchanged in v1.34.0):
src/icloudpd/authentication.py (request_2fa), src/icloudpd/base.py
(notificator_builder calls the notification script synchronously BEFORE
request_2fa), src/icloudpd/download.py ([DRY RUN] lines).

Environment:
  ICLOUDPD_SIM_MODE        ok | twofa | bad_password | fail | silent | busy_silent  (ok)
  ICLOUDPD_SIM_COUNT       files to "download" (2)
  ICLOUDPD_SIM_CODE        code Apple accepts in twofa mode (123456)
  ICLOUDPD_SIM_PHONES      trusted phone numbers (1)
  ICLOUDPD_SIM_SHARED_LIB  extra library printed by --list-libraries
  ICLOUDPD_SIM_SECONDS     duration of silent/busy_silent (3)
  ICLOUDPD_SIM_SLEEP       pause between downloads (0)
  ICLOUDPD_SIM_ARGV_OUT    append argv as a JSON line to this file
  ICLOUDPD_SIM_PREFIX      folder under --directory for new files (2026/10)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime


ALPHABET = "abcdefghijklmnopqrstuvwxyz"


def log(level: str, msg: str, stream: object = None) -> None:
    out = stream or sys.stdout
    out.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {level:<8} {msg}\n")  # type: ignore[attr-defined]
    out.flush()  # type: ignore[attr-defined]


def prompt(text: str) -> str:
    sys.stdout.write(f"{text}: ")
    sys.stdout.flush()
    line = sys.stdin.readline()
    if line == "":
        raise EOFError("EOF when reading a line")
    return line.strip()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="icloudpd", allow_abbrev=False)
    p.add_argument("--username", required=True)
    p.add_argument("--directory")
    p.add_argument("--mfa-provider")
    p.add_argument("--password-provider")
    p.add_argument("--cookie-directory")
    p.add_argument("--notification-script")
    p.add_argument("--domain")
    p.add_argument("--library")
    p.add_argument("--album")
    p.add_argument("--size", action="append")
    p.add_argument("--live-photo-size")
    p.add_argument("--align-raw")
    p.add_argument("--file-match-policy")
    p.add_argument("--live-photo-mov-filename-policy")
    p.add_argument("--folder-structure")
    p.add_argument("--log-level")
    p.add_argument("--recent", type=int)
    p.add_argument("--until-found", type=int)
    p.add_argument("--keep-icloud-recent-days", type=int)
    p.add_argument("--threads-num", type=int)
    p.add_argument("--skip-created-before")
    p.add_argument("--skip-created-after")
    for flag in (
        "--auth-only",
        "--list-libraries",
        "--list-albums",
        "--dry-run",
        "--skip-videos",
        "--skip-photos",
        "--skip-live-photos",
        "--force-size",
        "--keep-unicode-in-filenames",
        "--set-exif-datetime",
        "--xmp-sidecar",
        "--auto-delete",
        "--delete-after-download",
        "--use-os-locale",
        "--no-progress-bar",
    ):
        p.add_argument(flag, action="store_true")
    return p


def two_factor(args: argparse.Namespace) -> None:
    log("INFO", "Two-factor authentication is required (2fa)")
    if args.notification_script:
        subprocess.call([args.notification_script])
    phones = int(os.environ.get("ICLOUDPD_SIM_PHONES", "1"))
    good = os.environ.get("ICLOUDPD_SIM_CODE", "123456")
    if phones > 0:
        for i in range(phones):
            print(f"  {ALPHABET[i]}: (•••) •••-••{12 + i}", flush=True)
        index_str = f"..{ALPHABET[phones - 1]}" if phones > 1 else ""
        while True:
            answer = prompt(
                "Please enter two-factor authentication code or device index "
                f"({ALPHABET[0]}{index_str}) to send SMS with a code"
            ).lower()
            if len(answer) == 1 and answer in ALPHABET[:phones]:
                code = prompt(
                    "Please enter two-factor authentication code that you received over SMS"
                )
                break
            if len(answer) == 6 and answer.isdigit():
                code = answer
                break
            print(
                f"Should be index ({ALPHABET[0]}{index_str}) or six-digit code. Try again",
                flush=True,
            )
    else:
        code = prompt("Please enter two-factor authentication code")
    if code != good:
        log("ERROR", "Code verification failed.")
        raise SystemExit("Failed to verify two-factor authentication code")
    log(
        "INFO",
        "Great, you're all set up. The script can now be run without user "
        "interaction until 2FA expires.",
    )


def busy(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    with tempfile.TemporaryFile() as fh:
        while time.monotonic() < deadline:
            fh.seek(0)
            fh.write(b"x" * 4096)
            fh.flush()
            fh.seek(0)
            fh.read()
            time.sleep(0.05)


def download(args: argparse.Namespace) -> None:
    count = int(os.environ.get("ICLOUDPD_SIM_COUNT", "2"))
    prefix = os.environ.get("ICLOUDPD_SIM_PREFIX", "2026/10")
    pause = float(os.environ.get("ICLOUDPD_SIM_SLEEP", "0"))
    log("INFO", f"Downloading {count} original photos and videos to {args.directory} ...")
    for i in range(1, count + 1):
        path = os.path.join(args.directory, prefix, f"IMG_{i:04d}.HEIC")
        if os.path.exists(path):
            continue  # upstream logs "already exists" at DEBUG only
        if args.dry_run:
            log("INFO", f"[DRY RUN] Would download {path}")
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(b"\0" * 64)
        log("INFO", f"Downloaded {path}")
        time.sleep(pause)


def main() -> int:  # noqa: C901 - flat mode dispatch mirrors the real CLI's flow
    args = build_parser().parse_args()
    if out := os.environ.get("ICLOUDPD_SIM_ARGV_OUT"):
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(sys.argv[1:]) + "\n")
    mode = os.environ.get("ICLOUDPD_SIM_MODE", "ok")
    seconds = float(os.environ.get("ICLOUDPD_SIM_SECONDS", "3"))
    if args.password_provider == "console":
        sys.stdin.readline()  # the password
    if mode == "bad_password":
        log("ERROR", "Invalid email/password combination.")
        return 1
    if mode == "fail":
        log("ERROR", "something went wrong", sys.stderr)
        return 2
    if mode == "silent":
        time.sleep(seconds)
        return 0
    if mode == "busy_silent":
        busy(seconds)
        return 0
    if mode == "twofa":
        two_factor(args)
    log("INFO", "Authentication completed successfully")
    if args.auth_only:
        return 0
    if args.list_libraries:
        print("PrimarySync", flush=True)
        if extra := os.environ.get("ICLOUDPD_SIM_SHARED_LIB"):
            print(extra, flush=True)
        return 0
    download(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
