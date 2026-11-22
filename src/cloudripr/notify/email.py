"""Email alerts through Apprise. Never raises into callers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import apprise

from cloudripr.store.db import StateDB
from cloudripr.store.settings import EmailSettings


log = logging.getLogger(__name__)
# Silence Apprise's own URL logging, which includes the SMTP password
logging.getLogger("apprise").setLevel(logging.CRITICAL)

Sender = Callable[[list[str], str, str], bool]

LAST_ERROR_KEY = "email_last_error"
REAUTH_EMAIL_KEY = "reauth_email_at"


def _q(value: str) -> str:
    return quote(value, safe="")


def _redact(text: str, urls: list[str], password: str | None) -> str:
    """Redact secrets from error messages before logging or storage."""
    redacted = text
    # Replace full URLs
    for url in urls:
        redacted = redacted.replace(url, "<mail url>")
    # Replace raw password and URL-quoted form
    if password:
        redacted = redacted.replace(password, "***")
        redacted = redacted.replace(_q(password), "***")
    return redacted


def build_urls(email: EmailSettings, smtp_password: str | None) -> list[str]:
    urls: list[str] = []
    if email.to and email.smtp_user and smtp_password:
        scheme = "mailto" if email.smtp_security == "none" else "mailtos"
        url = (
            f"{scheme}://{_q(email.smtp_user)}:{_q(smtp_password)}"
            f"@{email.smtp_host}:{email.smtp_port}"
            f"?to={_q(email.to)}&from={_q(email.smtp_user)}"
        )
        if email.smtp_security != "none":
            url += f"&mode={email.smtp_security}"
        urls.append(url)
    urls.extend(u.strip() for u in email.extra_urls if u.strip())
    return urls


def apprise_send(urls: list[str], title: str, body: str) -> bool:
    client = apprise.Apprise()
    for url in urls:
        if not client.add(url):
            raise ValueError("Email settings are invalid; check the SMTP host, port and addresses.")
    return bool(client.notify(title=title, body=body))


class Notifier:
    REMIND_EVERY = timedelta(hours=24)
    RETRY_FAILED = timedelta(hours=1)

    def __init__(
        self,
        *,
        settings: Callable[[], EmailSettings],
        smtp_password: Callable[[], str | None],
        db: StateDB,
        sender: Sender = apprise_send,
        timeout: float = 30.0,
    ) -> None:
        self._settings = settings
        self._smtp_password = smtp_password
        self._db = db
        self._sender = sender
        self._timeout = timeout

    @property
    def last_error(self) -> str | None:
        return self._db.kv_get(LAST_ERROR_KEY)

    def _body(self, text: str, path: str) -> str:
        base = self._settings().app_url
        return f"{text}\n\n{base.rstrip('/')}{path}" if base else text

    async def send(self, title: str, body: str) -> bool:
        password = self._smtp_password()
        urls = build_urls(self._settings(), password)
        if not urls:
            return False
        error: str | None = None
        try:
            ok = await asyncio.wait_for(
                asyncio.to_thread(self._sender, urls, title, body), self._timeout
            )
        except TimeoutError:
            ok, error = False, f"no answer within {self._timeout:g} s"
        except Exception as exc:  # a broken mail setup must never break a run
            ok, error = False, str(exc) or type(exc).__name__
        if ok:
            self._db.kv_delete(LAST_ERROR_KEY)
        else:
            message = error or "delivery failed"
            redacted = _redact(message, urls, password)
            self._db.kv_set(LAST_ERROR_KEY, f"{datetime.now(UTC).isoformat()} {redacted}")
            log.warning("email failed: %s", redacted)
        return ok

    def _stamp_reauth(self, now: datetime, ok: bool) -> None:
        # A failed send retries after RETRY_FAILED instead of a full day.
        if not ok:
            now = now - self.REMIND_EVERY + self.RETRY_FAILED
        self._db.kv_set(REAUTH_EMAIL_KEY, now.isoformat())

    async def reauth_needed(self, reason: str) -> None:
        now = datetime.now(UTC)
        self._stamp_reauth(now, ok=False)  # pending until the send returns
        ok = await self.send(
            "iCloud needs you to sign in again",
            self._body(
                f"{reason}\n\nBackups are paused. Open the app and tap Re-authenticate; "
                "it takes about a minute.",
                "/account/reauth",
            ),
        )
        self._stamp_reauth(now, ok)

    async def remind_if_due(self, now: datetime) -> bool:
        # Normalize naive now to UTC; treat unparseable stored value as due
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        last = self._db.kv_get(REAUTH_EMAIL_KEY)
        if last is None:
            return False
        try:
            last_dt = datetime.fromisoformat(last)
            if now - last_dt < self.REMIND_EVERY:
                return False
        except (ValueError, TypeError):
            # Corrupt stored value: treat as due
            pass
        self._stamp_reauth(now, ok=False)  # pending until the send returns
        ok = await self.send(
            "Reminder: iCloud still needs you to sign in again",
            self._body("Backups stay paused until you re-authenticate.", "/account/reauth"),
        )
        self._stamp_reauth(now, ok)
        return True

    def clear_reauth(self) -> None:
        self._db.kv_delete(REAUTH_EMAIL_KEY)

    async def run_failed(self, policy: str, run_id: str, reason: str) -> None:
        if self._settings().on_failure:
            await self.send(f"Backup failed: {policy}", self._body(reason, f"/runs/{run_id}"))

    async def run_succeeded(self, policy: str, run_id: str, downloaded: int) -> None:
        if self._settings().on_success:
            await self.send(
                f"Backup done: {policy}",
                self._body(f"{downloaded} new item(s) downloaded.", f"/runs/{run_id}"),
            )

    async def gate_blocked(
        self, policy: str, run_id: str, count: int, *, partial: bool = False
    ) -> None:
        amount = f"at least {count}" if partial else str(count)
        await self.send(
            f"Check needed before downloading: {policy}",
            self._body(
                f"A safety dry run found {amount} files that would be downloaded. "
                "Nothing was downloaded. Review the list in the app and approve it "
                "if it looks right.",
                f"/runs/{run_id}",
            ),
        )

    async def test(self) -> tuple[bool, str | None]:
        if not build_urls(self._settings(), self._smtp_password()):
            return False, "Email is not set up yet."
        ok = await self.send(
            "Test email from cloudripr", "If you can read this, email alerts work."
        )
        return ok, None if ok else self.last_error
