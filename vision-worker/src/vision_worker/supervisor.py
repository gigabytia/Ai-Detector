"""Owns worker components and their start/stop order. Contains no business rules."""

import asyncio
import logging

from redis.asyncio import Redis

from vision_worker.messaging.heartbeat import HeartbeatPublisher

logger = logging.getLogger(__name__)


class Supervisor:
    def __init__(self, redis: Redis, heartbeat: HeartbeatPublisher) -> None:
        self._redis = redis
        self._heartbeat = heartbeat
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def heartbeat(self) -> HeartbeatPublisher:
        return self._heartbeat

    async def start(self) -> None:
        self._stop.clear()
        self._tasks.append(asyncio.create_task(self._heartbeat.run(self._stop), name="heartbeat"))
        logger.info("worker started")

    async def stop(self) -> None:
        self._stop.set()
        for task in self._tasks:
            await task
        self._tasks.clear()
        await self._heartbeat.withdraw()
        await self._redis.aclose()
        logger.info("worker stopped")
