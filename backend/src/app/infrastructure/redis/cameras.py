"""Worker commands and camera runtime status in Redis."""

import logging
import uuid
from collections.abc import Sequence

from pydantic import ValidationError
from redis.asyncio import Redis

from ai_detector_core.cameras.status import CameraRuntimeStatus
from ai_detector_core.telemetry.commands import WorkerCommand
from ai_detector_core.telemetry.redis_keys import WORKER_COMMANDS_CHANNEL, camera_status_key

logger = logging.getLogger(__name__)


class RedisCommandPublisher:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def publish(self, command: WorkerCommand) -> None:
        await self._redis.publish(WORKER_COMMANDS_CHANNEL, command.model_dump_json())


class RedisCameraStatusReader:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_many(
        self, camera_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, CameraRuntimeStatus]:
        if not camera_ids:
            return {}
        raw_values = await self._redis.mget([camera_status_key(cid) for cid in camera_ids])
        statuses: dict[uuid.UUID, CameraRuntimeStatus] = {}
        for camera_id, raw in zip(camera_ids, raw_values, strict=True):
            if raw is None:
                continue
            try:
                statuses[camera_id] = CameraRuntimeStatus.model_validate_json(raw)
            except ValidationError:
                logger.exception(
                    "invalid camera status in redis", extra={"camera_id": str(camera_id)}
                )
        return statuses
