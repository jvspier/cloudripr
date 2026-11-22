"""Prove, with the real binary and a real Apple ID, that unattended runs stop at
the 2FA hook before icloudpd asks Apple to push a code.

It signs in with an EMPTY session directory, so Apple must ask for 2FA. The
user's real session in /data is never touched. The engine's second safety layer
(killing on the "Two-factor authentication is required" log line) is switched
off here so that the hook alone is what gets tested.
"""

from __future__ import annotations

from pathlib import Path

from cloudripr.engine.argv import base_args
from cloudripr.engine.hook import install_hook
from cloudripr.engine.logwriter import LogWriter
from cloudripr.engine.noninteractive import NonInteractiveRun
from cloudripr.store.account_store import Account


async def verify_hook(
    *,
    icloudpd_cmd: list[str],
    apple_id: str,
    domain: str,
    password: str,
    work_dir: Path,
    poll_interval: float = 1.0,
) -> tuple[bool, str]:
    session = work_dir / "session"
    markers = work_dir / "markers"
    session.mkdir(parents=True, exist_ok=True)
    markers.mkdir(parents=True, exist_ok=True)
    hook = install_hook(work_dir / "bin" / "2fa-hook")
    log_path = work_dir / "verify.log"
    writer = LogWriter(log_path)
    account = Account(apple_id=apple_id, domain=domain)  # type: ignore[arg-type]
    result = await NonInteractiveRun(
        [*icloudpd_cmd, *base_args(account, session), "--auth-only"],
        password=password,
        log=writer,
        hook_script=hook,
        marker_dir=markers,
        idle_timeout=120,
        poll_interval=poll_interval,
        kill_on_twofa_line=False,
    ).run()
    writer.close()
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    prompted = "Please enter" in text
    if result.bad_password:
        return False, "Apple rejected the password, so nothing was verified."
    if prompted:
        return False, (
            "FAILED: icloudpd reached the code prompt, so Apple may have pushed a code. "
            "Unattended runs are NOT protected; don't switch over yet."
        )
    if result.hook_fired:
        return True, "OK: the hook stopped icloudpd before it asked Apple for a code."
    if result.exit_code == 0:
        return False, "Apple did not ask for 2FA, so the hook could not be tested."
    return False, f"Inconclusive: icloudpd exited with code {result.exit_code}. See {log_path}."
