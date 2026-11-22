from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from cloudripr.auth import require_auth
from cloudripr.services import SMTP_SECRET, Services, get_services
from cloudripr.store.settings import ServerSettings


router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_auth)])


class SettingsBody(ServerSettings):
    # None keeps the stored SMTP password; "" clears it. Never returned.
    smtp_password: str | None = None


def _out(svc: Services) -> dict[str, Any]:
    data = svc.settings.current.model_dump(mode="json")
    data.pop("apprise", None)
    data["smtp_password_set"] = svc.secrets.get(SMTP_SECRET) is not None
    data["email_last_error"] = svc.notifier.last_error
    return data


@router.get("")
def get_settings(request: Request) -> dict[str, Any]:
    return _out(get_services(request))


@router.put("")
def put_settings(body: SettingsBody, request: Request) -> dict[str, Any]:
    svc = get_services(request)
    new = ServerSettings(
        **body.model_dump(exclude={"smtp_password", "apprise"}),
        apprise=svc.settings.current.apprise,  # legacy table round-trips untouched
    )
    svc.settings_store.save(new)
    svc.settings.current = new
    if body.smtp_password is not None:
        if body.smtp_password == "":
            svc.secrets.delete(SMTP_SECRET)
        else:
            svc.secrets.set(SMTP_SECRET, body.smtp_password)
    return _out(svc)


@router.post("/test-email")
async def test_email(request: Request) -> dict[str, Any]:
    ok, error = await get_services(request).notifier.test()
    return {"ok": ok, "error": error}
