"""App login: hash from env or a file, first-run setup, rate limit."""

from __future__ import annotations

import collections
import hashlib
import hmac
import os
import secrets
import tempfile
import threading
import time
import unicodedata
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware

from cloudripr.errors import ApiError, ValidationError
from cloudripr.store.fileio import write_atomic


SESSION_MAX_AGE = 60 * 60 * 24 * 90  # stay logged in on the phone for 90 days
MIN_PASSWORD_LENGTH = 8


def _normalize(password: str) -> bytes:
    return unicodedata.normalize("NFKC", password).encode("utf-8")


class Authenticator:
    def __init__(self, password_hash: str | None, *, hash_file: Path | None = None) -> None:
        stripped = password_hash.strip() if password_hash else ""
        self._env_hash = stripped or None
        self._file = hash_file
        self._setup_lock = threading.Lock()

    @property
    def current_hash(self) -> str | None:
        if self._env_hash is not None:
            return self._env_hash
        if self._file is not None and self._file.is_file():
            return self._file.read_text(encoding="utf-8").strip() or None
        return None

    @property
    def needs_setup(self) -> bool:
        return self.current_hash is None

    @staticmethod
    def hash(password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.scrypt(_normalize(password), salt=salt.encode(), n=16384, r=8, p=1)
        return f"scrypt${salt}${digest.hex()}"

    def verify(self, password: str) -> bool:
        stored = self.current_hash
        if stored is None:
            return False
        parts = stored.split("$")
        if len(parts) != 3 or parts[0] != "scrypt":
            return False
        _, salt, expected = parts
        got = hashlib.scrypt(_normalize(password), salt=salt.encode(), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(got, expected)

    def setup(self, password: str) -> None:
        if not self.needs_setup:
            raise ApiError("A password is already set.", status_code=409)
        if self._file is None:
            raise ApiError("Password setup is not available on this server.", status_code=409)
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"Use at least {MIN_PASSWORD_LENGTH} characters.", field="password"
            )
        digest = self.hash(password).encode("utf-8")  # slow; keep outside the lock
        with self._setup_lock:
            if not self.needs_setup:
                raise ApiError("A password is already set.", status_code=409)
            self._create_exclusive(self._file, digest)

    @staticmethod
    def _create_exclusive(path: Path, data: bytes) -> None:
        """Create `path` with mode 0600 and full contents, failing if it already exists."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
        try:
            os.write(fd, data)
            os.fsync(fd)
            os.close(fd)
            os.chmod(tmp, 0o600)
            try:
                os.link(tmp, path)
            except FileExistsError:
                raise ApiError("A password is already set.", status_code=409) from None
        finally:
            Path(tmp).unlink(missing_ok=True)


class LoginRateLimiter:
    def __init__(
        self,
        max_failures: int = 5,
        window: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_failures
        self._window = window
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: dict[str, collections.deque[float]] = {}

    def _recent(self, key: str) -> collections.deque[float]:
        failures = self._failures.get(key)
        if failures is None:
            return collections.deque()
        cutoff = self._clock() - self._window
        while failures and failures[0] <= cutoff:
            failures.popleft()
        if not failures:
            del self._failures[key]
        return failures

    def allowed(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) < self._max

    def try_acquire(self, key: str) -> bool:
        """Atomically check the limit and record this attempt. Call reset() on success."""
        with self._lock:
            if len(self._recent(key)) >= self._max:
                return False
            self._failures.setdefault(key, collections.deque()).append(self._clock())
            return True

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._recent(key)
            self._failures.setdefault(key, collections.deque()).append(self._clock())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


def load_or_create_session_key(path: Path) -> str:
    if path.is_file():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(32)
    write_atomic(path, value.encode("utf-8"), mode=0o600)
    return value


def install_session_middleware(app: FastAPI, *, secret: str, https_only: bool = False) -> None:
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret,
        session_cookie="cloudripr",
        max_age=SESSION_MAX_AGE,
        same_site="lax",
        https_only=https_only,
    )


def require_auth(request: Request) -> bool:
    authenticator: Authenticator = request.app.state.authenticator
    if authenticator.needs_setup:
        raise ApiError("Set a password first.", status_code=401)
    if not request.session.get("authed"):
        raise ApiError("Not authenticated", status_code=401)
    return True
