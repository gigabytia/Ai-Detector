"""Creates and closes process-wide resources. Nothing is created at import time."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_detector_core.ports.clock import SystemClock
from app.application.system_service import SystemService
from app.core.config import Settings
from app.infrastructure.database.session import DatabaseProbe, create_engine
from app.infrastructure.redis.client import (
    RedisProbe,
    RedisWorkerHeartbeatReader,
    create_redis,
)

logger = logging.getLogger(__name__)


@dataclass
class AppResources:
    engine: AsyncEngine
    redis: Redis
    system_service: SystemService


def build_resources(settings: Settings) -> AppResources:
    engine = create_engine(str(settings.database_url))
    redis = create_redis(str(settings.redis_url))
    redis_probe = RedisProbe(redis)
    system_service = SystemService(
        probes=[DatabaseProbe(engine), redis_probe],
        heartbeats=RedisWorkerHeartbeatReader(redis),
        redis_probe_name=redis_probe.name,
        clock=SystemClock(),
    )
    return AppResources(engine=engine, redis=redis, system_service=system_service)


async def close_resources(resources: AppResources) -> None:
    await resources.redis.aclose()
    await resources.engine.dispose()


def make_lifespan(settings: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resources = build_resources(settings)
        app.state.resources = resources
        logger.info("api started", extra={"app_env": settings.app_env})
        try:
            yield
        finally:
            await close_resources(resources)
            logger.info("api stopped")

    return lifespan
