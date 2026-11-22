from __future__ import annotations

import argparse
import os
import shlex
import sys
from importlib.resources import files
from pathlib import Path

from cloudripr.auth import Authenticator, load_or_create_session_key
from cloudripr.paths import DataPaths


def _default_static_dir() -> Path | None:
    try:
        p = Path(str(files("cloudripr").joinpath("web_dist")))
    except (ModuleNotFoundError, FileNotFoundError):
        return None
    return p if p.exists() else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cloudripr")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    parser.add_argument(
        "--data-dir", default=os.environ.get("DATA_DIR", str(Path.home() / ".cloudripr"))
    )
    parser.add_argument(
        "--cache-dir",
        default=os.environ.get("CACHE_DIR"),
        help="Disposable cache (library index, thumbnails). Default: <data-dir>/cache",
    )
    parser.add_argument("--password-hash", default=os.environ.get("CLOUDRIPR_PASSWORD_HASH"))
    parser.add_argument("--session-secret", default=os.environ.get("CLOUDRIPR_SESSION_SECRET"))
    parser.add_argument(
        "--https-only",
        action="store_true",
        default=os.environ.get("CLOUDRIPR_HTTPS_ONLY") == "1",
        help="Only send the login cookie over HTTPS (behind an HTTPS reverse proxy).",
    )
    sub = parser.add_subparsers(dest="cmd")
    init_pw = sub.add_parser("init-password", help="Hash a password and print it")
    init_pw.add_argument("password")
    verify = sub.add_parser(
        "verify-2fa-hook",
        help="Check that unattended runs stop before Apple pushes a 2FA code",
    )
    verify.add_argument("--apple-id", required=True)
    verify.add_argument("--domain", default="com", choices=["com", "cn"])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.cmd == "init-password":
        print(Authenticator.hash(args.password))
        return 0

    if args.cmd == "verify-2fa-hook":
        import asyncio
        import getpass
        import tempfile

        from cloudripr.tools import verify_hook as vh

        password = getpass.getpass("Apple ID password: ")
        with tempfile.TemporaryDirectory(prefix="icloudpd-verify-") as tmp:
            ok, message = asyncio.run(
                vh.verify_hook(
                    icloudpd_cmd=["icloudpd"],
                    apple_id=args.apple_id,
                    domain=args.domain,
                    password=password,
                    work_dir=Path(tmp),
                )
            )
        print(message)
        return 0 if ok else 1

    data_dir = Path(args.data_dir)
    paths = DataPaths(data_dir, Path(args.cache_dir) if args.cache_dir else data_dir / "cache")
    paths.ensure()
    authenticator = Authenticator(args.password_hash, hash_file=paths.app / "login.hash")
    if authenticator.needs_setup:
        print("No login password set yet: open the app to choose one.", file=sys.stderr)
    session_secret = args.session_secret or load_or_create_session_key(paths.app / "session.key")

    import uvicorn

    from cloudripr.app import create_app

    app = create_app(
        paths=paths,
        authenticator=authenticator,
        session_secret=session_secret,
        https_only=args.https_only,
        static_dir=_default_static_dir(),
        # Development/testing only: run against tests/fixtures/icloudpd_sim.py.
        icloudpd_cmd=shlex.split(os.environ.get("CLOUDRIPR_ICLOUDPD_CMD", "icloudpd")),
    )
    uvicorn.run(app, host=args.host, port=args.port)
    return 0
