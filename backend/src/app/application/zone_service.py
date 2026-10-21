"""Camera-scoped zone CRUD, locking parent for concurrent creation and soft deletion."""

import logging
from uuid import UUID, uuid4

from redis.exceptions import RedisError
from sqlalchemy import select

from ai_detector_core.ports.clock import Clock
from ai_detector_core.telemetry.commands import WorkerCommand, WorkerCommandType
from ai_detector_core.zones.model import ZoneShape
from app.application.camera_service import CommandPublisher
from app.application.errors import CameraNotFoundError, UnprocessableError, ZoneNotFoundError
from app.infrastructure.database.models import CameraModel, ZoneModel
from app.infrastructure.database.repositories.zones import ZoneRepository
from app.schemas.zones import ZoneRead

logger = logging.getLogger(__name__)
MAX_ZONES_PER_CAMERA = 16


def read_zone(row: ZoneModel) -> ZoneRead:
    return ZoneRead(
        id=row.id,
        camera_id=row.camera_id,
        name=row.name,
        points=row.points,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ZoneService:
    def __init__(
        self, repository: ZoneRepository, commands: CommandPublisher, clock: Clock
    ) -> None:
        self._repo, self._commands, self._clock = repository, commands, clock

    async def _require_camera(self, camera_id: UUID, *, lock: bool = False) -> None:
        query = select(CameraModel).where(
            CameraModel.id == camera_id, CameraModel.deleted_at.is_(None)
        )
        if lock:
            query = query.with_for_update()
        if await self._repo.session.scalar(query) is None:
            raise CameraNotFoundError

    async def list(self, camera_id: UUID) -> list[ZoneRead]:
        await self._require_camera(camera_id)
        return [read_zone(z) for z in await self._repo.list(camera_id)]

    async def save(self, camera_id: UUID, body: ZoneShape, zone_id: UUID | None = None) -> ZoneRead:
        await self._require_camera(camera_id, lock=True)
        now = self._clock.now()
        if zone_id is None:
            if len(await self._repo.list(camera_id)) >= MAX_ZONES_PER_CAMERA:
                raise UnprocessableError("At most 16 zones per camera")
            row = ZoneModel(id=uuid4(), camera_id=camera_id, created_at=now)
            self._repo.session.add(row)
        else:
            found = await self._repo.get(camera_id, zone_id)
            if found is None:
                raise ZoneNotFoundError
            row = found
        row.name, row.enabled, row.updated_at = body.name, body.enabled, now
        row.points = [{"x": p.x, "y": p.y} for p in body.points]
        result = read_zone(row)
        await self._repo.session.commit()
        await self._notify(camera_id)
        return result

    async def delete(self, camera_id: UUID, zone_id: UUID) -> None:
        await self._require_camera(camera_id, lock=True)
        row = await self._repo.get(camera_id, zone_id)
        if row is None:
            raise ZoneNotFoundError
        await self._repo.session.delete(row)
        await self._repo.session.commit()
        await self._notify(camera_id)

    async def _notify(self, camera_id: UUID) -> None:
        try:
            await self._commands.publish(
                WorkerCommand(type=WorkerCommandType.CAMERA_CHANGED, camera_id=camera_id)
            )
        except RedisError:
            logger.exception("zone notification not delivered", extra={"camera_id": str(camera_id)})
