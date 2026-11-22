"""Server settings, stored in settings.toml."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, Literal

import tomli_w
from pydantic import BaseModel, Field, field_validator

from cloudripr.store.fileio import write_atomic


_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class EmailSettings(BaseModel):
    to: str | None = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str | None = None
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    extra_urls: list[str] = Field(default_factory=list)
    on_failure: bool = True
    on_success: bool = False
    app_url: str | None = None


class ServerSettings(BaseModel):
    email: EmailSettings = Field(default_factory=EmailSettings)
    retention_runs: int = Field(default=30, ge=1, le=1000)
    idle_timeout_minutes: int = Field(default=30, ge=1, le=24 * 60)
    # Container-local "HH:MM" for the daily session check; "" disables it.
    session_check_time: str = "19:00"
    gate_threshold: int = Field(default=100, ge=0)
    # The previous app's [apprise] table, kept verbatim so a rollback still finds it.
    apprise: dict[str, Any] = Field(default_factory=dict)

    @field_validator("session_check_time")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        v = v.strip()
        if v and not _HHMM.match(v):
            raise ValueError("use HH:MM (24-hour), or leave empty to disable")
        return v


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> ServerSettings:
        if not self._path.exists():
            return ServerSettings()
        data = tomllib.loads(self._path.read_text(encoding="utf-8"))
        return ServerSettings(**data)

    def save(self, settings: ServerSettings) -> None:
        payload = tomli_w.dumps(settings.model_dump(mode="json", exclude_none=True))
        write_atomic(self._path, payload.encode("utf-8"))
