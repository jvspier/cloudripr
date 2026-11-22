"""Server-sent events: account, re-auth attempt and run updates."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from cloudripr.auth import require_auth
from cloudripr.services import Services, get_services


router = APIRouter(tags=["events"], dependencies=[Depends(require_auth)])


def _sse(kind: str, seq: int, data: object) -> bytes:
    return f"id: {seq}\nevent: {kind}\ndata: {json.dumps(data)}\n\n".encode()


async def event_stream(
    svc: Services,
    is_disconnected: Callable[[], Awaitable[bool]],
    *,
    keepalive: float = 15.0,
) -> AsyncIterator[bytes]:
    queue = svc.bus.subscribe()
    try:
        yield _sse(
            "hello",
            0,
            {
                "account": svc.account.snapshot(),
                "runs": [r.to_json() for r in svc.runs.in_flight()],
            },
        )
        while not await is_disconnected():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=keepalive)
            except TimeoutError:
                yield b": keepalive\n\n"
                continue
            yield _sse(event["type"], event["seq"], event["data"])
    finally:
        svc.bus.unsubscribe(queue)


@router.get("/events")
async def events(request: Request) -> StreamingResponse:
    return StreamingResponse(
        event_stream(get_services(request), request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
