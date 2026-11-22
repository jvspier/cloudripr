from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from cloudripr.auth import Authenticator, LoginRateLimiter
from cloudripr.errors import ApiError


router = APIRouter(prefix="/auth", tags=["auth"])


class PasswordBody(BaseModel):
    password: str


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/status")
def status(request: Request) -> dict[str, bool]:
    authenticator: Authenticator = request.app.state.authenticator
    return {
        "authenticated": not authenticator.needs_setup and bool(request.session.get("authed")),
        "setup_required": authenticator.needs_setup,
    }


@router.post("/setup")
def setup(body: PasswordBody, request: Request) -> dict[str, bool]:
    authenticator: Authenticator = request.app.state.authenticator
    authenticator.setup(body.password)
    request.session["authed"] = True
    return {"ok": True}


@router.post("/login")
def login(body: PasswordBody, request: Request) -> dict[str, bool]:
    authenticator: Authenticator = request.app.state.authenticator
    limiter: LoginRateLimiter = request.app.state.login_limiter
    if authenticator.needs_setup:
        raise ApiError("Set a password first.", status_code=409)
    key = _client_key(request)
    if not limiter.try_acquire(key):
        raise ApiError("Too many attempts. Wait a minute and try again.", status_code=429)
    if not authenticator.verify(body.password):
        raise ApiError("Wrong password.", status_code=401)
    limiter.reset(key)
    request.session["authed"] = True
    return {"ok": True}


@router.post("/logout")
def logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}
