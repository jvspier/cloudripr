from __future__ import annotations

from cloudripr.events import EventBus


async def test_publish_fans_out_with_sequence() -> None:
    bus = EventBus()
    a, b = bus.subscribe(), bus.subscribe()
    bus.publish("run", {"id": "r1"})
    bus.publish("account", {"state": "ok"})
    assert a.get_nowait() == {"seq": 1, "type": "run", "data": {"id": "r1"}}
    assert a.get_nowait()["seq"] == 2
    assert b.qsize() == 2


async def test_unsubscribe_and_full_queue_never_raise() -> None:
    bus = EventBus(max_queue=1)
    q = bus.subscribe()
    bus.publish("x", {})
    bus.publish("x", {})  # queue full: dropped, no exception
    assert q.qsize() == 1
    bus.unsubscribe(q)
    bus.publish("x", {})
    assert q.qsize() == 1
