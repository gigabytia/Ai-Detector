"""Bounded retry queue; atomic Stream + live publish, UUID makes retries idempotent.

RAM queue survives Redis outages, not process crashes. Once Redis acknowledges,
its durability depends on Redis persistence/replication (see ADR-034).
"""

import asyncio
import contextlib
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ai_detector_core.events.domain import DomainEvent
from ai_detector_core.telemetry.event_bus import (
    EVENTS_LIVE,
    INGEST_STREAM,
    pending_event_key,
)

logger = logging.getLogger(__name__)
PUBLISH = """
local id = redis.call('XADD', KEYS[1], '*', 'event', ARGV[1])
redis.call('SET', KEYS[3], '1', 'EX', 86400)
redis.call('PUBLISH', KEYS[2], ARGV[1])
return id
"""


class EventPublisher:
    def __init__(self, redis: Redis, capacity: int = 1000) -> None:
        self.redis = redis
        self.queue: asyncio.Queue[DomainEvent] = asyncio.Queue(maxsize=capacity)
        self.healthy = True
        self.dropped = 0

    def offer(self, event: DomainEvent) -> None:
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1
            self.healthy = False
            logger.critical("event outbox full; event lost", extra={"event_id": str(event.id)})

    async def publish(self, event: DomainEvent) -> None:
        await self.redis.eval(
            PUBLISH,
            3,
            INGEST_STREAM,
            EVENTS_LIVE,
            pending_event_key(event.id),
            event.model_dump_json(),
        )

    async def run(self, stop: asyncio.Event) -> None:
        pending: DomainEvent | None = None
        delay = 0.25
        while not stop.is_set():
            if pending is None:
                try:
                    pending = await asyncio.wait_for(self.queue.get(), timeout=0.25)
                except TimeoutError:
                    continue
            try:
                await self.publish(pending)
            except (RedisError, OSError):
                self.healthy = False
                logger.warning("event delivery delayed", extra={"event_id": str(pending.id)})
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                delay = min(delay * 2, 5)
            else:
                self.queue.task_done()
                pending = None
                self.healthy = self.dropped == 0
                delay = 0.25
        # Best effort bounded flush; no unbounded shutdown on a failed Redis.
        try:
            async with asyncio.timeout(2):
                if pending is not None:
                    await self.publish(pending)
                    self.queue.task_done()
                    pending = None
                while not self.queue.empty():
                    pending = self.queue.get_nowait()
                    await self.publish(pending)
                    self.queue.task_done()
                    pending = None
        except (RedisError, OSError, TimeoutError):
            logger.error(
                "shutdown with undelivered events",
                extra={"undelivered": self.queue.qsize() + int(pending is not None)},
            )
