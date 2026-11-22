from __future__ import annotations

import asyncio
import json
from pathlib import Path

from cloudripr.api.events import event_stream
from cloudripr.paths import DataPaths
from cloudripr.services import build_services
from tests.helpers import SIM_CMD, FakeSender


def parse(chunk: bytes) -> tuple[str, dict]:
    lines = dict(line.split(": ", 1) for line in chunk.decode().strip().splitlines())
    return lines["event"], json.loads(lines["data"])


async def test_stream_says_hello_then_forwards_events(tmp_path: Path) -> None:
    svc = build_services(
        DataPaths(tmp_path / "d", tmp_path / "c"),
        icloudpd_cmd=SIM_CMD,
        icloudpd_version="1.32.3",
        sender=FakeSender(),
    )
    disconnected = False

    async def is_disconnected() -> bool:
        return disconnected

    stream = event_stream(svc, is_disconnected, keepalive=0.05)
    kind, data = parse(await stream.__anext__())
    assert kind == "hello"
    assert data["account"]["state"] == "unknown"
    assert data["runs"] == []
    svc.bus.publish("run", {"id": "r1"})
    kind, data = parse(await stream.__anext__())
    assert (kind, data) == ("run", {"id": "r1"})
    assert await stream.__anext__() == b": keepalive\n\n"
    disconnected = True
    rest = [chunk async for chunk in stream]
    assert rest == [] or rest == [b": keepalive\n\n"]
    await asyncio.sleep(0)
