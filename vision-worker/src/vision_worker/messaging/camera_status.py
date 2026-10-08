"""Publishes runtime status of every session to Redis once per second (TTL 5 s)."""

import asyncio
import logging
import uuid
from collections.abc import Callable, Sequence

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ai_detector_core.cameras.status import CameraRuntimeStatus
from ai_detector_core.telemetry.redis_keys import CAMERA_STATUS_TTL_SECONDS, camera_status_key

logger = logging.getLogger(__name__)

PUBLISH_INTERVAL_SECONDS = 1.0


class CameraStatusPublisher:
    def __init__(self, redis: Redis, statuses: Callable[[], Sequence[CameraRuntimeStatus]]) -> None:
        self._redis = redis
        self._statuses = statuses
        self._published: set[uuid.UUID] = set()
        self._healthy = True

    async def publish_once(self) -> None:
        statuses = self._statuses()
        current = {status.camera_id for status in statuses}
        gone = self._published - current
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                for status in statuses:
                    pipe.set(
                        camera_status_key(status.camera_id),
                        status.model_dump_json(),
                        ex=CAMERA_STATUS_TTL_SECONDS,
                    )
                for camera_id in gone:
                    pipe.delete(camera_status_key(camera_id))
                await pipe.execute()
        except RedisError:
            if self._healthy:
                logger.exception("camera status not published")
            self._healthy = False
            return
        self._healthy = True
        self._published = current

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.publish_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=PUBLISH_INTERVAL_SECONDS)
            except TimeoutError:
                continue
