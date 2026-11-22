from __future__ import annotations

import asyncio

from cloudripr.engine.lock import AccountLock


async def test_priority_then_fifo() -> None:
    lock = AccountLock()
    order: list[str] = []
    release = asyncio.Event()

    async def first() -> None:
        async with lock.hold(AccountLock.RUN, "run:a"):
            order.append("run:a")
            await release.wait()

    async def take(priority: int, label: str) -> None:
        async with lock.hold(priority, label):
            order.append(label)

    t1 = asyncio.create_task(first())
    await asyncio.sleep(0)
    assert lock.holder == "run:a"
    t2 = asyncio.create_task(take(AccountLock.RUN, "run:b"))
    t3 = asyncio.create_task(take(AccountLock.RUN, "run:c"))
    await asyncio.sleep(0)
    t4 = asyncio.create_task(take(AccountLock.REAUTH, "reauth"))
    await asyncio.sleep(0)
    assert lock.waiting() == ["reauth", "run:b", "run:c"]
    release.set()
    await asyncio.gather(t1, t2, t3, t4)
    assert order == ["run:a", "reauth", "run:b", "run:c"]
    assert lock.holder is None


async def test_cancelled_waiter_does_not_block() -> None:
    lock = AccountLock()
    release = asyncio.Event()

    async def hold() -> None:
        async with lock.hold(AccountLock.RUN, "a"):
            await release.wait()

    async def wait_for_it(label: str) -> str:
        async with lock.hold(AccountLock.RUN, label):
            return label

    t1 = asyncio.create_task(hold())
    await asyncio.sleep(0)
    t2 = asyncio.create_task(wait_for_it("b"))
    t3 = asyncio.create_task(wait_for_it("c"))
    await asyncio.sleep(0)
    t2.cancel()
    release.set()
    assert await t3 == "c"
    await t1
    assert lock.holder is None
    assert lock.waiting() == []
