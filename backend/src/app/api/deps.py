"""FastAPI dependencies. One AsyncSession per request; services are built per request."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_detector_core.cameras.config import CameraConfig
from app.application.analytics_service import AnalyticsService
from app.application.camera_config_service import CameraConfigService
from app.application.camera_service import CameraService
from app.application.event_service import EventService
from app.application.line_service import LineService
from app.application.system_service import SystemService
from app.application.worker_spec_service import WorkerSpecService
from app.application.zone_service import ZoneService
from app.core.lifecycle import AppResources
from app.infrastructure.database.repositories.analytics import AnalyticsRepository
from app.infrastructure.database.repositories.cameras import CameraRepository
from app.infrastructure.database.repositories.events import EventRepository
from app.infrastructure.database.repositories.lines import LineRepository
from app.infrastructure.database.repositories.zones import ZoneRepository
from app.infrastructure.redis.cameras import RedisCameraStatusReader, RedisCommandPublisher


def get_resources(request: Request) -> AppResources:
    resources: AppResources = request.app.state.resources
    return resources


Resources = Annotated[AppResources, Depends(get_resources)]


def get_system_service(resources: Resources) -> SystemService:
    return resources.system_service


async def get_session(resources: Resources) -> AsyncIterator[AsyncSession]:
    async with resources.session_factory() as session:
        yield session


Session = Annotated[AsyncSession, Depends(get_session)]


def get_camera_service(resources: Resources, session: Session) -> CameraService:
    return CameraService(
        repository=CameraRepository(session),
        commands=RedisCommandPublisher(resources.redis),
        statuses=RedisCameraStatusReader(resources.redis),
        uploads=resources.uploads,
        clock=resources.clock,
        max_cameras=resources.settings.max_cameras,
    )


def get_config_defaults(resources: Resources) -> CameraConfig:
    return CameraConfig(
        snapshot_enabled=resources.settings.snapshot_enabled,
        loitering_threshold_seconds=resources.settings.loitering_threshold_seconds,
        zone_enter_dwell_seconds=resources.settings.zone_enter_dwell_seconds,
        zone_exit_grace_seconds=resources.settings.zone_exit_grace_seconds,
        event_cooldown_seconds=resources.settings.event_cooldown_seconds,
        target_fps=resources.settings.target_fps,
        detection_confidence=resources.settings.detection_confidence,
    )


def get_camera_config_service(resources: Resources, session: Session) -> CameraConfigService:
    return CameraConfigService(
        session, RedisCommandPublisher(resources.redis), get_config_defaults(resources)
    )


def get_worker_spec_service(resources: Resources, session: Session) -> WorkerSpecService:
    return WorkerSpecService(CameraRepository(session), session, get_config_defaults(resources))


def get_zone_service(resources: Resources, session: Session) -> ZoneService:
    return ZoneService(
        ZoneRepository(session), RedisCommandPublisher(resources.redis), resources.clock
    )


def get_event_service(resources: Resources, session: Session) -> EventService:
    return EventService(
        EventRepository(session), resources.redis, resources.clock, resources.csv_export_slots
    )


def get_line_service(resources: Resources, session: Session) -> LineService:
    return LineService(
        LineRepository(session), RedisCommandPublisher(resources.redis), resources.clock
    )


def get_analytics_service(resources: Resources, session: Session) -> AnalyticsService:
    return AnalyticsService(
        AnalyticsRepository(session), RedisCameraStatusReader(resources.redis), resources.clock
    )
