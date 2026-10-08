"""Builds CameraSpec objects for workers (internal API, ADR-002)."""

import uuid

from ai_detector_core.cameras.source import SourceType
from ai_detector_core.cameras.spec import CameraSpec
from app.application.errors import CameraNotFoundError
from app.infrastructure.database.models import CameraModel
from app.infrastructure.database.repositories.cameras import CameraRepository


def to_spec(camera: CameraModel) -> CameraSpec:
    return CameraSpec(
        id=camera.id,
        name=camera.name,
        source_type=SourceType(camera.source_type),
        source_url=camera.source_url,
        enabled=camera.enabled,
    )


class WorkerSpecService:
    def __init__(self, repository: CameraRepository) -> None:
        self._repo = repository

    async def enabled_specs(self) -> list[CameraSpec]:
        return [to_spec(camera) for camera in await self._repo.list_enabled()]

    async def spec(self, camera_id: uuid.UUID) -> CameraSpec:
        camera = await self._repo.get_active(camera_id)
        if camera is None:
            raise CameraNotFoundError
        return to_spec(camera)
