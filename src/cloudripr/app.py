from __future__ import annotations

import asyncio
import importlib.metadata
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import compile_path, get_route_path

from cloudripr.api import account as account_api
from cloudripr.api import auth as auth_api
from cloudripr.api import events as events_api
from cloudripr.api import library as library_api
from cloudripr.api import policies as policies_api
from cloudripr.api import runs as runs_api
from cloudripr.api import settings as settings_api
from cloudripr.auth import Authenticator, LoginRateLimiter, install_session_middleware
from cloudripr.errors import ApiError, install_handlers
from cloudripr.notify.email import Sender, apprise_send
from cloudripr.paths import DataPaths
from cloudripr.services import build_services
from cloudripr.static import install_static


def detect_icloudpd_version() -> str:
    try:
        return importlib.metadata.version("icloudpd")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def create_app(
    *,
    paths: DataPaths,
    authenticator: Authenticator,
    session_secret: str,
    https_only: bool = False,
    icloudpd_cmd: list[str] | None = None,
    icloudpd_version: str | None = None,
    static_dir: Path | None = None,
    sender: Sender = apprise_send,
    start_scheduler: bool = True,
    poll_interval: float = 1.0,
) -> FastAPI:
    svc = build_services(
        paths,
        icloudpd_cmd=icloudpd_cmd or ["icloudpd"],
        icloudpd_version=icloudpd_version or detect_icloudpd_version(),
        sender=sender,
        poll_interval=poll_interval,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(svc.scheduler.run_forever()) if start_scheduler else None
        try:
            yield
        finally:
            svc.scheduler.stop()
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            await svc.runs.shutdown()
            await svc.account.shutdown()

    app = FastAPI(
        title="cloudripr",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    install_handlers(app)
    install_session_middleware(app, secret=session_secret, https_only=https_only)
    app.state.services = svc
    app.state.authenticator = authenticator
    app.state.login_limiter = LoginRateLimiter()
    # (path regex, methods) of every real API route, for telling 405 from 404 below.
    # Built from our own routers: FastAPI does not expose included routes as a flat list.
    api_routes: list[tuple[re.Pattern[str], set[str]]] = []
    for router in (
        auth_api.router,
        account_api.router,
        policies_api.router,
        runs_api.router,
        settings_api.router,
        events_api.router,
        library_api.router,
    ):
        app.include_router(router, prefix="/api")
        for route in router.routes:
            methods = getattr(route, "methods", None)
            if methods:
                api_routes.append((compile_path("/api" + route.path)[0], set(methods)))

    @app.api_route(
        "/api/{rest:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )
    async def _unknown_api(request: Request) -> None:
        # A real route with another method is a 405, not a 404.
        path = get_route_path(request.scope)
        allowed: set[str] = set()
        for regex, methods in api_routes:
            if regex.match(path):
                allowed |= methods
        if allowed:
            raise StarletteHTTPException(
                405, "Method Not Allowed", headers={"Allow": ", ".join(sorted(allowed))}
            )
        raise ApiError("Not found", status_code=404)

    install_static(app, static_dir)  # last: its catch-all must not shadow /api
    return app
