"""FastAPI dependencies. One AsyncSession per request; services are built per request."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.camera_service import CameraService
from app.application.system_service import SystemService
from app.application.worker_spec_service import WorkerSpecService
from app.core.lifecycle import AppResources
from app.infrastructure.database.repositories.cameras import CameraRepository
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


def get_worker_spec_service(session: Session) -> WorkerSpecService:
    return WorkerSpecService(CameraRepository(session))
