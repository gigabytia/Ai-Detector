import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from ai_detector_core.events.domain import DomainEvent, ZoneEntryMetadata
from app.api.v1.events import decode_cursor, stream
from app.application.errors import UnprocessableError
from app.core.lifecycle import AppResources
from app.infrastructure.redis.live import LiveHub, sse
from vision_worker.messaging.events import EventPublisher


def event() -> DomainEvent:
    return DomainEvent(
        camera_id=uuid4(),
        run_id=uuid4(),
        track_id=1,
        zone_id=uuid4(),
        occurred_at=datetime.now(UTC),
        source_ts_ms=1,
        detector_confidence=0.8,
        event_confidence=0.7,
        message="Вход",
        metadata=ZoneEntryMetadata(
            bbox=(0.1, 0.1, 0.5, 0.5), anchor=(0.3, 0.5), dwell_seconds=1, stability=0.9
        ),
    )


def test_live_fanout_overflow_disconnects_only_slow_subscriber() -> None:
    hub = LiveHub(cast(Redis, object()))
    slow = hub.subscribe()
    fast = hub.subscribe()
    for _ in range(129):
        hub.broadcast(sse("test", "{}"))
        assert fast.get_nowait() is not None
    assert slow.get_nowait() is None
    assert slow not in hub.subscribers
    hub.unsubscribe(fast)
    assert not hub.subscribers


def test_outbox_is_bounded_and_does_not_silently_drop() -> None:
    publisher = EventPublisher(cast(Redis, object()), capacity=1)
    publisher.offer(event())
    publisher.offer(event())
    assert publisher.queue.qsize() == 1
    assert publisher.dropped == 1 and not publisher.healthy


async def test_outbox_retries_same_uuid_after_redis_outage() -> None:
    class Publisher(EventPublisher):
        def __init__(self, redis: Redis) -> None:
            super().__init__(redis)
            self.ids: list[str] = []

        async def publish(self, e: DomainEvent) -> None:
            self.ids.append(str(e.id))
            if len(self.ids) == 1:
                raise RedisConnectionError("down")
            stop.set()

    stop = asyncio.Event()
    publisher = Publisher(cast(Redis, object()))
    original = event()
    publisher.offer(original)
    await asyncio.wait_for(publisher.run(stop), 2)
    assert publisher.ids == [str(original.id)] * 2
    assert publisher.queue.empty() and publisher.healthy


@pytest.mark.parametrize("cursor", ["!!!", "e30=", "WyJhIiwgImIiXQ==", "W251bGwsbnVsbF0="])
def test_bad_cursor_is_client_error(cursor: str) -> None:
    with pytest.raises(UnprocessableError):
        decode_cursor(cursor)


async def test_sse_iterator_releases_queue_when_connection_closes() -> None:
    from types import SimpleNamespace

    from fastapi import Request

    hub = LiveHub(cast(Redis, object()))
    resources = cast(AppResources, SimpleNamespace(live=hub))
    request = Request({"type": "http"})
    response = await stream(request, resources)
    iterator = cast(AsyncGenerator[str, None], response.body_iterator)
    first = await anext(iterator)
    assert "unavailable" in str(first) and len(hub.subscribers) == 1
    await iterator.aclose()
    assert not hub.subscribers


def test_telemetry_hub_keeps_only_latest_metadata() -> None:
    import json
    from dataclasses import replace

    import numpy as np

    from vision_worker.cameras.frame import Frame
    from vision_worker.pipeline.results import DetectionResult
    from vision_worker.pipeline.telemetry import TelemetryHub

    camera_id = uuid4()
    hub = TelemetryHub()
    queue = hub.subscribe(camera_id)
    frame = Frame(np.zeros((8, 8, 3), dtype=np.uint8), 1, 0, datetime.now(UTC))
    result = DetectionResult(camera_id, uuid4(), frame, (), 2)
    hub.offer(result)
    hub._last.clear()  # advance throttle deterministically
    hub.offer(replace(result, frame=replace(frame, frame_id=2)))
    assert queue.qsize() == 1
    packet = json.loads(queue.get_nowait())
    assert packet["frame_id"] == 2 and packet["persons"] == 0 and "jpeg" not in packet
    hub.unsubscribe(camera_id, queue)
    assert not hub._subscribers and not hub._last


async def test_stopped_background_delivery_makes_probe_fail() -> None:
    from app.infrastructure.redis.tasks import EventTasksProbe

    probe = EventTasksProbe()
    with pytest.raises(RuntimeError):
        await probe.check()
    stop = asyncio.Event()

    async def running() -> None:
        await stop.wait()

    probe.tasks = [asyncio.create_task(running()), asyncio.create_task(running())]
    await probe.check()
    stop.set()
    await asyncio.gather(*probe.tasks)
    with pytest.raises(RuntimeError):
        await probe.check()
