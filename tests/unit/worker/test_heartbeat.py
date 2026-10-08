import asyncio
import json

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from ai_detector_core.telemetry.redis_keys import WORKER_HEARTBEAT_TTL_SECONDS
from fakes import FixedClock
from vision_worker.messaging.heartbeat import HeartbeatPublisher


class FakeStore:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, int]] = {}
        self.fail = False

    async def set(self, name: str, value: str, ex: int) -> object:
        if self.fail:
            raise RedisConnectionError("down")
        self.values[name] = (value, ex)
        return True

    async def delete(self, *names: str) -> object:
        for name in names:
            self.values.pop(name, None)
        return len(names)


def make_publisher(store: FakeStore, clock: FixedClock) -> HeartbeatPublisher:
    return HeartbeatPublisher(store=store, worker_id="w1", version="0.1.0", clock=clock)


async def test_publishes_heartbeat_with_ttl() -> None:
    store, clock = FakeStore(), FixedClock()
    publisher = make_publisher(store, clock)
    clock.advance(3)
    await publisher.publish_once()

    value, ttl = store.values["ad:worker:w1:heartbeat"]
    assert ttl == WORKER_HEARTBEAT_TTL_SECONDS
    payload = json.loads(value)
    assert payload["worker_id"] == "w1"
    assert payload["sent_at"] == "2026-01-01T12:00:03Z"
    assert publisher.redis_ok
    assert publisher.last_published_at == clock.now()


async def test_redis_failure_marks_not_ok_and_recovers(caplog: pytest.LogCaptureFixture) -> None:
    store, clock = FakeStore(), FixedClock()
    publisher = make_publisher(store, clock)
    await publisher.publish_once()

    store.fail = True
    await publisher.publish_once()
    await publisher.publish_once()
    assert not publisher.redis_ok
    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 1, "error is logged once per outage, not every second"

    store.fail = False
    await publisher.publish_once()
    assert publisher.redis_ok


async def test_run_stops_on_event_and_withdraw_removes_key() -> None:
    store, clock = FakeStore(), FixedClock()
    publisher = make_publisher(store, clock)
    stop = asyncio.Event()
    task = asyncio.create_task(publisher.run(stop))
    await asyncio.sleep(0)
    stop.set()
    await asyncio.wait_for(task, timeout=1)
    assert "ad:worker:w1:heartbeat" in store.values

    await publisher.withdraw()
    assert store.values == {}
