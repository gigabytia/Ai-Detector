"""Redis connection and read helpers used by the API."""

import logging

from pydantic import ValidationError
from redis.asyncio import Redis

from ai_detector_core.telemetry.heartbeat import WorkerHeartbeat
from ai_detector_core.telemetry.redis_keys import WORKER_HEARTBEAT_PATTERN

logger = logging.getLogger(__name__)


def create_redis(redis_url: str) -> "Redis":
    return Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)


class RedisProbe:
    name = "redis"

    def __init__(self, redis: "Redis") -> None:
        self._redis = redis

    async def check(self) -> None:
        await self._redis.ping()


class RedisWorkerHeartbeatReader:
    """Reads live worker heartbeats; expired keys mean the worker is gone."""

    def __init__(self, redis: "Redis") -> None:
        self._redis = redis

    async def list_heartbeats(self) -> list[WorkerHeartbeat]:
        keys = [key async for key in self._redis.scan_iter(match=WORKER_HEARTBEAT_PATTERN)]
        if not keys:
            return []
        heartbeats: list[WorkerHeartbeat] = []
        for key, raw in zip(keys, await self._redis.mget(keys), strict=True):
            if raw is None:
                continue  # expired between SCAN and MGET
            try:
                heartbeats.append(WorkerHeartbeat.model_validate_json(raw))
            except ValidationError:
                logger.exception("invalid worker heartbeat", extra={"redis_key": str(key)})
        return sorted(heartbeats, key=lambda item: item.worker_id)
