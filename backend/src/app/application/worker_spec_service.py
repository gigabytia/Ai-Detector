"""Builds CameraSpec objects for workers (internal API, ADR-002)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ai_detector_core.cameras.config import CameraConfig
from ai_detector_core.cameras.source import SourceType
from ai_detector_core.cameras.spec import CameraSpec
from ai_detector_core.lines.model import LineSpec
from ai_detector_core.zones.model import ZoneSpec
from app.application.camera_config_service import config_overrides
from app.application.errors import CameraNotFoundError
from app.application.line_service import read_line
from app.application.zone_service import read_zone
from app.infrastructure.database.models import CameraConfigModel, CameraModel
from app.infrastructure.database.repositories.cameras import CameraRepository
from app.infrastructure.database.repositories.lines import LineRepository
from app.infrastructure.database.repositories.zones import ZoneRepository


def to_spec(
    camera: CameraModel,
    config: CameraConfig,
    zones: tuple[ZoneSpec, ...] = (),
    lines: tuple[LineSpec, ...] = (),
) -> CameraSpec:
    return CameraSpec(
        id=camera.id,
        name=camera.name,
        source_type=SourceType(camera.source_type),
        source_url=camera.source_url,
        enabled=camera.enabled,
        config=config,
        zones=zones,
        lines=lines,
    )


class WorkerSpecService:
    def __init__(
        self, repository: CameraRepository, session: AsyncSession, defaults: CameraConfig
    ) -> None:
        self._repo = repository
        self._session = session
        self._defaults = defaults

    async def _zones(self, camera_id: uuid.UUID) -> tuple[ZoneSpec, ...]:
        return tuple(
            ZoneSpec.model_validate(read_zone(z).model_dump(exclude={"created_at", "updated_at"}))
            for z in await ZoneRepository(self._session).list(camera_id)
        )

    async def _lines(self, camera_id: uuid.UUID) -> tuple[LineSpec, ...]:
        return tuple(
            LineSpec.model_validate(
                read_line(line).model_dump(exclude={"created_at", "updated_at"})
            )
            for line in await LineRepository(self._session).list(camera_id)
        )

    async def _config(self, camera_id: uuid.UUID) -> CameraConfig:
        return config_overrides(await self._session.get(CameraConfigModel, camera_id)).resolve(
            self._defaults
        )

    async def enabled_specs(self) -> list[CameraSpec]:
        return [
            to_spec(
                camera,
                await self._config(camera.id),
                await self._zones(camera.id),
                await self._lines(camera.id),
            )
            for camera in await self._repo.list_enabled()
        ]

    async def spec(self, camera_id: uuid.UUID) -> CameraSpec:
        camera = await self._repo.get_active(camera_id)
        if camera is None:
            raise CameraNotFoundError
        return to_spec(
            camera,
            await self._config(camera.id),
            await self._zones(camera.id),
            await self._lines(camera.id),
        )
