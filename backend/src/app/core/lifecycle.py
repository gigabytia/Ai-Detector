"""Creates and closes process-wide resources. Nothing is created at import time."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ai_detector_core.ports.clock import Clock, SystemClock
from ai_detector_core.storage.snapshots import LocalSnapshotStorage
from app.application.system_service import SystemService
from app.core.config import Settings
from app.infrastructure.database.session import (
    DatabaseProbe,
    create_engine,
    create_session_factory,
)
from app.infrastructure.redis.analytics import AnalyticsIngest
from app.infrastructure.redis.client import (
    RedisProbe,
    RedisWorkerHeartbeatReader,
    create_redis,
)
from app.infrastructure.redis.ingest import EventIngest
from app.infrastructure.redis.live import LiveHub
from app.infrastructure.redis.tasks import EventTasksProbe, report_task_failure
from app.infrastructure.storage.snapshot_retention import SnapshotRetention
from app.infrastructure.storage.uploads import LocalUploadStorage

logger = logging.getLogger(__name__)


@dataclass
class AppResources:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    clock: Clock
    uploads: LocalUploadStorage
    system_service: SystemService
    live: LiveHub | None = None
    event_tasks: EventTasksProbe = field(default_factory=EventTasksProbe)
    analytics_tasks: EventTasksProbe = field(
        default_factory=lambda: EventTasksProbe(1, "analytics_ingest")
    )


def build_resources(settings: Settings) -> AppResources:
    engine = create_engine(str(settings.database_url))
    redis = create_redis(str(settings.redis_url))
    clock = SystemClock()
    redis_probe = RedisProbe(redis)
    event_tasks = EventTasksProbe()
    analytics_tasks = EventTasksProbe(1, "analytics_ingest")
    system_service = SystemService(
        probes=[DatabaseProbe(engine), redis_probe, event_tasks, analytics_tasks],
        heartbeats=RedisWorkerHeartbeatReader(redis),
        redis_probe_name=redis_probe.name,
        clock=clock,
    )
    uploads = LocalUploadStorage(
        root=settings.upload_path,
        max_bytes=settings.upload_max_bytes,
        allowed_extensions=settings.upload_allowed_extensions,
    )
    return AppResources(
        settings=settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        redis=redis,
        clock=clock,
        uploads=uploads,
        system_service=system_service,
        event_tasks=event_tasks,
        analytics_tasks=analytics_tasks,
    )


async def close_resources(resources: AppResources) -> None:
    await resources.redis.aclose()
    await resources.engine.dispose()


def make_lifespan(settings: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resources = build_resources(settings)
        app.state.resources = resources
        resources.live = LiveHub(resources.redis)
        stop = asyncio.Event()
        tasks = [
            asyncio.create_task(
                EventIngest(
                    resources.redis, resources.session_factory, settings.snapshot_retention_days
                ).run(stop),
                name="event-ingest",
            ),
            asyncio.create_task(resources.live.run(stop), name="event-live"),
            asyncio.create_task(
                AnalyticsIngest(resources.redis, resources.session_factory).run(stop),
                name="analytics-ingest",
            ),
        ]
        resources.event_tasks.tasks = tasks[:2]
        resources.analytics_tasks.tasks = tasks[2:3]
        maintenance = asyncio.create_task(
            SnapshotRetention(
                resources.redis,
                resources.session_factory,
                LocalSnapshotStorage(settings.snapshot_path),
                settings.snapshot_retention_days,
                settings.snapshot_cleanup_interval_seconds,
            ).run(stop),
            name="snapshot-retention",
        )
        tasks = [*tasks, maintenance]
        for task in tasks:
            task.add_done_callback(report_task_failure)
        logger.info("api started", extra={"app_env": settings.app_env})
        try:
            yield
        finally:
            stop.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await close_resources(resources)
            logger.info("api stopped")

    return lifespan
