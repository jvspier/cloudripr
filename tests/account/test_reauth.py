from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from cloudripr.account.reauth import AttemptError, PhoneOption, ReauthAttempt, mask_phone
from cloudripr.engine.logwriter import LogWriter
from tests.helpers import SIM_CMD, eventually


def make(
    tmp_path: Path,
    *,
    timeout: float = 10.0,
    states: list[str] | None = None,
    argv: list[str] | None = None,
) -> ReauthAttempt:
    return ReauthAttempt(
        attempt_id="a1",
        argv=argv
        or [
            *SIM_CMD,
            "--username",
            "u@example.com",
            "--password-provider",
            "console",
            "--mfa-provider",
            "console",
            "--auth-only",
        ],
        password="pw",
        log=LogWriter(tmp_path / "a1.log"),
        timeout=timeout,
        on_change=(lambda a: states.append(a.state)) if states is not None else None,
    )


@pytest.fixture(autouse=True)
def twofa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "twofa")


def test_mask_phone() -> None:
    assert mask_phone("(•••) •••-••12") == "•••• 12"
    assert mask_phone("+31 •• ••• ••34") == "•••• 34"
    assert mask_phone("••••") == "••••"


async def test_push_code_success(tmp_path: Path) -> None:
    states: list[str] = []
    a = make(tmp_path, states=states)
    await a.start()
    await eventually(lambda: a.state == "awaiting_code")
    assert a.phones == [PhoneOption("a", "•••• 12")]
    await a.submit_code(" 123456 ")
    assert await a.wait() == "succeeded"
    assert states[-3:] == ["awaiting_code", "verifying", "succeeded"]
    assert a.ended_at is not None
    assert "Great, you're all set up" in (tmp_path / "a1.log").read_text()


async def test_wrong_code_is_rejected(tmp_path: Path) -> None:
    a = make(tmp_path)
    await a.start()
    await eventually(lambda: a.state == "awaiting_code")
    await a.submit_code("000000")
    assert await a.wait() == "rejected"
    assert a.error == "Apple rejected that code."


async def test_sms_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_PHONES", "2")
    a = make(tmp_path)
    await a.start()
    await eventually(lambda: a.state == "awaiting_code")
    assert [p.masked for p in a.phones] == ["•••• 12", "•••• 13"]
    await a.request_sms("b")
    assert a.sms_sent_to == "•••• 13"
    await eventually(lambda: a.state == "awaiting_sms_code")
    await a.submit_code("123456")
    assert await a.wait() == "succeeded"


async def test_code_only_prompt_without_phones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_PHONES", "0")
    a = make(tmp_path)
    await a.start()
    await eventually(lambda: a.state == "awaiting_code")
    assert a.phones == []
    with pytest.raises(AttemptError):
        await a.request_sms("a")
    await a.submit_code("123456")
    assert await a.wait() == "succeeded"


async def test_bad_password(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "bad_password")
    a = make(tmp_path)
    await a.start()
    assert await a.wait() == "bad_password"
    assert "Settings → Account" in (a.error or "")


async def test_valid_session_needs_no_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICLOUDPD_SIM_MODE", "ok")
    a = make(tmp_path)
    await a.start()
    assert await a.wait() == "succeeded"


async def test_input_validation(tmp_path: Path) -> None:
    a = make(tmp_path)
    with pytest.raises(AttemptError, match="Not waiting"):
        await a.submit_code("123456")  # still "starting"
    await a.start()
    await eventually(lambda: a.state == "awaiting_code")
    with pytest.raises(AttemptError, match="6-digit"):
        await a.submit_code("12ab")
    with pytest.raises(AttemptError, match="Unknown phone"):
        await a.request_sms("z")
    await a.cancel()
    await a.wait()


async def test_expires(tmp_path: Path) -> None:
    a = make(tmp_path, timeout=0.5)
    await a.start()
    assert await a.wait() == "expired"
    assert a.error is not None
    assert "timed out" in a.error


async def test_cancel(tmp_path: Path) -> None:
    a = make(tmp_path)
    await a.start()
    await eventually(lambda: a.state == "awaiting_code")
    await a.cancel()
    assert await a.wait() == "cancelled"
    with pytest.raises(AttemptError):
        await a.submit_code("123456")


async def test_cancel_before_start(tmp_path: Path) -> None:
    a = make(tmp_path)
    await a.cancel()
    await a.start()  # no-op
    assert await a.wait() == "cancelled"


async def test_cancel_while_process_is_starting(tmp_path: Path) -> None:
    """Final review: a cancel in the spawn window must not leave icloudpd running."""
    a = make(tmp_path)
    starting = asyncio.create_task(a.start())
    await asyncio.sleep(0)
    await a.cancel()
    await starting
    assert await asyncio.wait_for(a.wait(), 5) == "cancelled"
    assert a._proc is not None
    assert a._proc.returncode is not None


async def test_spawn_failure(tmp_path: Path) -> None:
    a = make(tmp_path, argv=["/nonexistent/icloudpd"])
    await a.start()
    assert await a.wait() == "failed"


async def test_snapshot(tmp_path: Path) -> None:
    a = make(tmp_path)
    snap = a.snapshot()
    assert snap["id"] == "a1"
    assert snap["state"] == "starting"
    assert snap["phones"] == []
    assert snap["ended_at"] is None
    assert snap["started_at"].endswith("+00:00")
