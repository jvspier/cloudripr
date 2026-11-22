from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from cloudripr import __version__
from cloudripr.account.reauth import CODE_RE, AttemptError
from cloudripr.account.service import AccountNotConfigured, RunInProgress
from cloudripr.auth import require_auth
from cloudripr.errors import ApiError, ValidationError
from cloudripr.migration import NOTES_KEY
from cloudripr.services import Services, get_services


router = APIRouter(prefix="/account", tags=["account"], dependencies=[Depends(require_auth)])


class AccountBody(BaseModel):
    apple_id: str | None = None
    domain: Literal["com", "cn"] | None = None
    password: str | None = None


class CodeBody(BaseModel):
    code: str


class SmsBody(BaseModel):
    index: str


def _snapshot(svc: Services) -> dict[str, Any]:
    data = svc.account.snapshot()
    data["migration_notes"] = svc.db.kv_get_json(NOTES_KEY) or []
    data["versions"] = {"app": __version__, "icloudpd": svc.icloudpd_version}
    data["email_last_error"] = svc.notifier.last_error
    session = svc.paths.session
    data["has_session"] = session.is_dir() and any(session.iterdir())
    return data


def _attempt(svc: Services) -> dict[str, Any]:
    attempt = svc.account.current_attempt()
    return {"attempt": attempt.snapshot() if attempt else None}


@router.get("")
def get_account(request: Request) -> dict[str, Any]:
    return _snapshot(get_services(request))


@router.put("")
def put_account(body: AccountBody, request: Request) -> dict[str, Any]:
    svc = get_services(request)
    if body.apple_id is None and svc.account_store.load() is None:
        raise ValidationError("Enter your Apple ID first.", field="apple_id")
    if body.password is not None and body.password == "":
        raise ValidationError("The password can't be empty.", field="password")
    try:
        svc.account.update(apple_id=body.apple_id, domain=body.domain, password=body.password)
    except PydanticValidationError as exc:
        raise ValidationError(
            exc.errors()[0]["msg"].removeprefix("Value error, "), field="apple_id"
        ) from None
    return _snapshot(svc)


@router.post("/dismiss-notes")
def dismiss_notes(request: Request) -> dict[str, bool]:
    get_services(request).db.kv_delete(NOTES_KEY)
    return {"ok": True}


async def _start(svc: Services, *, restart: bool) -> dict[str, Any]:
    try:
        attempt = await (svc.account.restart_reauth() if restart else svc.account.start_reauth())
    except AccountNotConfigured as exc:
        raise ApiError(str(exc), status_code=422) from None
    except RunInProgress as exc:
        raise ApiError(str(exc), status_code=409) from None
    return attempt.snapshot()


@router.post("/reauth")
async def start_reauth(request: Request) -> dict[str, Any]:
    return await _start(get_services(request), restart=False)


@router.post("/reauth/restart")
async def restart_reauth(request: Request) -> dict[str, Any]:
    return await _start(get_services(request), restart=True)


@router.get("/reauth")
def get_reauth(request: Request) -> dict[str, Any]:
    return _attempt(get_services(request))


@router.post("/reauth/code")
async def submit_code(body: CodeBody, request: Request) -> dict[str, Any]:
    svc = get_services(request)
    if not CODE_RE.match(body.code.strip()):
        raise ValidationError("Enter the 6-digit code.", field="code")
    try:
        await svc.account.submit_code(body.code)
    except AttemptError as exc:
        raise ApiError(str(exc), status_code=409) from None
    return _attempt(svc)


@router.post("/reauth/sms")
async def request_sms(body: SmsBody, request: Request) -> dict[str, Any]:
    svc = get_services(request)
    try:
        await svc.account.request_sms(body.index)
    except AttemptError as exc:
        raise ApiError(str(exc), status_code=409) from None
    return _attempt(svc)


@router.delete("/reauth")
async def cancel_reauth(request: Request) -> dict[str, bool]:
    await get_services(request).account.cancel_reauth()
    return {"ok": True}


@router.get("/attempts")
def list_attempts(request: Request) -> list[dict[str, Any]]:
    return [a.to_json() for a in get_services(request).db.list_attempts()]


@router.get("/attempts/{attempt_id}/log")
def attempt_log(attempt_id: str, request: Request) -> FileResponse:
    svc = get_services(request)
    record = svc.db.get_attempt(attempt_id)
    if record is None or not record.log_path:
        raise ApiError("Log not found", status_code=404)
    path = Path(record.log_path).resolve()
    if not path.is_relative_to(svc.paths.auth_logs.resolve()) or not path.is_file():
        raise ApiError("Log not found", status_code=404)
    return FileResponse(path, media_type="text/plain")
