"""In-process event fan-out for the SSE stream."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any


class EventBus:
    """Publishers never block: a subscriber whose queue is full misses events and
    re-syncs over REST when it reconnects."""

    def __init__(self, max_queue: int = 1000) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._seq = 0
        self._max_queue = max_queue

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._max_queue)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(q)

    def publish(self, kind: str, data: dict[str, Any]) -> None:
        self._seq += 1
        event = {"seq": self._seq, "type": kind, "data": data}
        for q in list(self._subscribers):
            with suppress(asyncio.QueueFull):
                q.put_nowait(event)
