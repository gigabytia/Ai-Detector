"""Publishes the worker heartbeat to Redis once per second with a short TTL."""

import asyncio
import logging
from collections.abc import Awaitable
from datetime import datetime
from typing import Protocol

from redis.exceptions import RedisError

from ai_detector_core.ports.clock import Clock
from ai_detector_core.telemetry.heartbeat import WorkerHeartbeat
from ai_detector_core.telemetry.redis_keys import (
    WORKER_HEARTBEAT_TTL_SECONDS,
    worker_heartbeat_key,
)

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 1.0


class HeartbeatStore(Protocol):
    """Subset of redis.asyncio.Redis used here; lets tests pass a fake."""

    def set(self, name: str, value: str, ex: int) -> Awaitable[object]: ...

    def delete(self, *names: str) -> Awaitable[object]: ...


class HeartbeatPublisher:
    def __init__(self, store: HeartbeatStore, worker_id: str, version: str, clock: Clock) -> None:
        self._store = store
        self._worker_id = worker_id
        self._version = version
        self._clock = clock
        self._started_at = clock.now()
        self._last_published_at: datetime | None = None
        self._redis_ok = False

    @property
    def redis_ok(self) -> bool:
        return self._redis_ok

    @property
    def last_published_at(self) -> datetime | None:
        return self._last_published_at

    async def publish_once(self) -> None:
        """Send one heartbeat. Redis errors are logged on state change and reflected in health."""
        now = self._clock.now()
        heartbeat = WorkerHeartbeat(
            worker_id=self._worker_id,
            version=self._version,
            started_at=self._started_at,
            sent_at=now,
        )
        try:
            await self._store.set(
                worker_heartbeat_key(self._worker_id),
                heartbeat.model_dump_json(),
                ex=WORKER_HEARTBEAT_TTL_SECONDS,
            )
        except RedisError:
            if self._redis_ok or self._last_published_at is None:
                logger.exception("redis unavailable, worker is degraded")
            self._redis_ok = False
            return
        if not self._redis_ok:
            logger.info("redis connection ok", extra={"worker_id": self._worker_id})
        self._redis_ok = True
        self._last_published_at = now

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.publish_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_INTERVAL_SECONDS)
            except TimeoutError:
                continue

    async def withdraw(self) -> None:
        """Remove the heartbeat on graceful shutdown so the UI sees the worker leave at once."""
        try:
            await self._store.delete(worker_heartbeat_key(self._worker_id))
        except RedisError:
            logger.exception("failed to remove heartbeat on shutdown")
