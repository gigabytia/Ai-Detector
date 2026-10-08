"""Development seed: mock cameras so the UI is not empty after the first start (§109).

Idempotent: cameras that already exist by name are left untouched.
Zones and sample events are added to the seed together with those features.
"""

import asyncio
import logging

from ai_detector_core.cameras.source import SourceType
from ai_detector_core.ports.clock import SystemClock
from app.application.camera_service import CameraService
from app.application.errors import CameraNameConflictError
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.infrastructure.database.repositories.cameras import CameraRepository
from app.infrastructure.database.session import create_engine, create_session_factory
from app.infrastructure.redis.cameras import RedisCameraStatusReader, RedisCommandPublisher
from app.infrastructure.redis.client import create_redis
from app.infrastructure.storage.uploads import LocalUploadStorage

logger = logging.getLogger(__name__)

SEED_CAMERAS = [
    ("Склад — проход", "mock://walk_through"),
    ("Цех — два человека", "mock://two_people"),
]


async def seed() -> None:
    settings = get_settings()
    engine = create_engine(str(settings.database_url))
    redis = create_redis(str(settings.redis_url))
    uploads = LocalUploadStorage(
        settings.upload_path, settings.upload_max_bytes, settings.upload_allowed_extensions
    )
    try:
        async with create_session_factory(engine)() as session:
            service = CameraService(
                repository=CameraRepository(session),
                commands=RedisCommandPublisher(redis),
                statuses=RedisCameraStatusReader(redis),
                uploads=uploads,
                clock=SystemClock(),
                max_cameras=settings.max_cameras,
            )
            for name, url in SEED_CAMERAS:
                try:
                    await service.create_camera(name, SourceType.MOCK, url, enabled=True)
                    logger.info("seed camera created", extra={"camera_name": name})
                except CameraNameConflictError:
                    logger.info("seed camera exists", extra={"camera_name": name})
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    configure_logging(get_settings())
    asyncio.run(seed())
