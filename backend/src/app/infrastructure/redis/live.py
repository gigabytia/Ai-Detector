"""One pubsub connection per API process; bounded fan-out for SSE clients.

Pub/sub has no replay. A reconnect (Redis or browser) explicitly requests REST
resync. A slow client is disconnected rather than silently losing alarms.
"""

import asyncio
import contextlib
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ai_detector_core.events.domain import DomainEvent
from ai_detector_core.telemetry.event_bus import CAMERAS_STATUS, EVENTS_LIVE, EVENTS_UPDATES
from app.schemas.events import EventRead

logger = logging.getLogger(__name__)


def sse(kind: str, payload: str) -> str:
    # JSON payloads never contain literal line breaks; other payloads are encoded too.
    return f"event: {kind}\ndata: {payload}\n\n"


class LiveHub:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self.available = False
        self.subscribers: set[asyncio.Queue[str | None]] = set()

    def subscribe(self) -> asyncio.Queue[str | None]:
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=128)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str | None]) -> None:
        self.subscribers.discard(queue)

    def broadcast(self, packet: str) -> None:
        for queue in tuple(self.subscribers):
            if queue.full():
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
                self.subscribers.discard(queue)
            else:
                queue.put_nowait(packet)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                async with self.redis.pubsub(ignore_subscribe_messages=True) as pubsub:
                    await pubsub.subscribe(EVENTS_LIVE, EVENTS_UPDATES, CAMERAS_STATUS)
                    self.available = True
                    self.broadcast(sse("resync", "{}"))
                    while not stop.is_set():
                        message = await pubsub.get_message(timeout=0.5)
                        if message is None:
                            continue
                        channel = message["channel"].decode()
                        if channel == EVENTS_LIVE:
                            try:
                                event = DomainEvent.model_validate_json(message["data"])
                            except ValueError:
                                logger.warning("invalid live event ignored")
                                continue
                            self.broadcast(sse("event.created", event.model_dump_json()))
                        elif channel == EVENTS_UPDATES:
                            try:
                                updated = EventRead.model_validate_json(message["data"])
                            except ValueError:
                                logger.warning("invalid event update ignored")
                                continue
                            self.broadcast(sse("event.updated", updated.model_dump_json()))
                        else:
                            self.broadcast(sse("camera.status", "{}"))
            except (RedisError, OSError):
                logger.warning("live connection interrupted")
                self.available = False
                self.broadcast(sse("unavailable", "{}"))
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=1)
