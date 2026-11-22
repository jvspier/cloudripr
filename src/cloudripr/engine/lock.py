"""Serialises every icloudpd process.

All invocations share one session directory that icloudpd rewrites on every
request, so only one may run at a time. Lower priority value wins; FIFO
within a priority.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class AccountLock:
    REAUTH = 0
    RUN = 1

    def __init__(self) -> None:
        self._holder: str | None = None
        self._waiters: list[tuple[int, int, asyncio.Future[None], str]] = []
        self._counter = itertools.count()

    @property
    def holder(self) -> str | None:
        return self._holder

    def waiting(self) -> list[str]:
        return [label for _, _, _, label in sorted(self._waiters, key=lambda w: (w[0], w[1]))]

    @asynccontextmanager
    async def hold(self, priority: int, label: str) -> AsyncIterator[None]:
        if self._holder is None and not self._waiters:
            self._holder = label
        else:
            fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            entry = (priority, next(self._counter), fut, label)
            heapq.heappush(self._waiters, entry)
            try:
                await fut
            except asyncio.CancelledError:
                if entry in self._waiters:
                    self._waiters.remove(entry)
                    heapq.heapify(self._waiters)
                elif fut.done() and not fut.cancelled():
                    self._release()  # handed the lock, then cancelled: pass it on
                raise
        try:
            yield
        finally:
            self._release()

    def _release(self) -> None:
        self._holder = None
        while self._waiters:
            _, _, fut, label = heapq.heappop(self._waiters)
            if not fut.done():
                self._holder = label
                fut.set_result(None)
                return
