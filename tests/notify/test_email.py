from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import apprise
import pytest

from cloudripr.notify.email import Notifier, build_urls
from cloudripr.store.db import StateDB
from cloudripr.store.settings import EmailSettings
from tests.helpers import EMAIL, FakeSender


def notifier(
    tmp_path: Path,
    sender: FakeSender,
    email: EmailSettings = EMAIL,
    password: str | None = "pw",
    timeout: float = 30.0,
) -> tuple[Notifier, StateDB]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = StateDB(tmp_path / "s.db")
    return Notifier(
        settings=lambda: email,
        smtp_password=lambda: password,
        db=db,
        sender=sender,
        timeout=timeout,
    ), db


def parsed(url: str) -> apprise.NotifyBase:
    client = apprise.Apprise()
    assert client.add(url)
    return client[0]


def test_build_urls_requires_complete_setup() -> None:
    assert build_urls(EmailSettings(), "pw") == []
    assert build_urls(EMAIL, None) == []


@pytest.mark.parametrize(
    ("security", "port", "mode", "secure"),
    [
        ("starttls", 587, "starttls", True),
        ("ssl", 465, "ssl", True),
        ("none", 25, "insecure", False),
    ],
)
def test_build_urls_parse_in_apprise(security: str, port: int, mode: str, secure: bool) -> None:
    email = EMAIL.model_copy(
        update={"smtp_security": security, "smtp_port": port, "smtp_host": "smtp.example.com"}
    )
    url = build_urls(email, "p@ss word")[0]
    plugin = parsed(url)
    assert plugin.smtp_host == "smtp.example.com"
    assert plugin.port == port
    assert plugin.secure is secure
    assert plugin.secure_mode == mode
    assert plugin.targets == [(False, "me@example.com")]
    assert plugin.password == "p@ss word"


def test_extra_urls_appended() -> None:
    email = EMAIL.model_copy(update={"extra_urls": [" json://x ", ""]})
    assert build_urls(email, "pw")[1:] == ["json://x"]


async def test_send_without_setup_does_nothing(tmp_path: Path) -> None:
    sender = FakeSender()
    n, _ = notifier(tmp_path, sender, email=EmailSettings())
    assert await n.send("t", "b") is False
    assert sender.calls == []


async def test_failures_are_recorded_and_cleared(tmp_path: Path) -> None:
    sender = FakeSender(error=RuntimeError("smtp down"))
    n, _ = notifier(tmp_path, sender)
    assert await n.send("t", "b") is False
    assert n.last_error is not None
    assert "smtp down" in n.last_error
    sender.error = None
    assert await n.send("t", "b") is True
    assert n.last_error is None


async def test_slow_server_times_out(tmp_path: Path) -> None:
    n, _ = notifier(tmp_path, FakeSender(delay=0.5), timeout=0.1)
    assert await n.send("t", "b") is False
    assert "no answer" in (n.last_error or "")


async def test_reauth_email_and_daily_reminder(tmp_path: Path) -> None:
    sender = FakeSender()
    n, _ = notifier(tmp_path, sender)
    await n.reauth_needed("Apple asked for a new sign-in.")
    assert sender.titles == ["iCloud needs you to sign in again"]
    assert "http://nas:5000/account/reauth" in sender.calls[0][2]
    now = datetime.now(UTC)
    assert await n.remind_if_due(now + timedelta(hours=1)) is False
    assert await n.remind_if_due(now + timedelta(hours=25)) is True
    assert sender.titles[-1].startswith("Reminder")
    n.clear_reauth()
    assert await n.remind_if_due(now + timedelta(days=5)) is False


async def test_run_events_respect_toggles(tmp_path: Path) -> None:
    sender = FakeSender()
    n, _ = notifier(tmp_path, sender)
    await n.run_failed("icloud", "r1", "boom")
    await n.run_succeeded("icloud", "r2", 3)  # on_success defaults to off
    await n.gate_blocked("icloud", "r3", 150)  # always on
    assert sender.titles == ["Backup failed: icloud", "Check needed before downloading: icloud"]
    assert "http://nas:5000/runs/r1" in sender.calls[0][2]
    assert "150" in sender.calls[1][2]


async def test_test_email(tmp_path: Path) -> None:
    n, _ = notifier(tmp_path, FakeSender(), email=EmailSettings())
    assert await n.test() == (False, "Email is not set up yet.")
    n2, _ = notifier(tmp_path / "b", FakeSender())
    assert await n2.test() == (True, None)


async def test_password_not_leaked_in_errors(tmp_path: Path) -> None:
    sender = FakeSender(error=RuntimeError("failed mailtos://pw@host/inbox"))
    n, _ = notifier(tmp_path, sender, password="pw")
    assert await n.send("t", "b") is False
    error = n.last_error
    assert error is not None
    assert "pw" not in error
    # Quoted form should also be redacted
    assert "***" in error


async def test_invalid_extra_url_raises_value_error(tmp_path: Path) -> None:
    from cloudripr.notify.email import apprise_send

    with pytest.raises(ValueError, match="Email settings are invalid"):
        apprise_send(["notaurl://x"], "t", "b")


async def test_invalid_extra_url_in_send(tmp_path: Path) -> None:
    from cloudripr.notify.email import apprise_send

    email = EMAIL.model_copy(update={"extra_urls": ["notaurl://x"]})
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = StateDB(tmp_path / "s.db")
    n = Notifier(
        settings=lambda: email,
        smtp_password=lambda: "pw",
        db=db,
        sender=apprise_send,
    )
    assert await n.send("t", "b") is False
    error = n.last_error
    assert error is not None
    assert "notaurl://x" not in error
    assert "Email settings are invalid" in error


async def test_remind_if_due_with_corrupt_value(tmp_path: Path) -> None:
    sender = FakeSender()
    n, db = notifier(tmp_path, sender)
    # Store a corrupt value
    db.kv_set("reauth_email_at", "not a datetime")
    now = datetime.now(UTC)
    # Should treat corrupt value as due
    assert await n.remind_if_due(now) is True
    assert sender.titles[-1].startswith("Reminder")


async def test_remind_if_due_with_naive_now(tmp_path: Path) -> None:
    sender = FakeSender()
    n, db = notifier(tmp_path, sender)
    # Store a reauth timestamp
    db.kv_set("reauth_email_at", datetime.now(UTC).isoformat())
    # Call with naive datetime (no tzinfo)
    naive_now = datetime.now() + timedelta(hours=25)
    # Should work without raising
    result = await n.remind_if_due(naive_now)
    assert result is True
