"""Camera-scoped line CRUD, locking parent for concurrent creation and soft deletion."""

import logging
from uuid import UUID, uuid4

from redis.exceptions import RedisError
from sqlalchemy import select

from ai_detector_core.lines.model import LineShape
from ai_detector_core.ports.clock import Clock
from ai_detector_core.telemetry.commands import WorkerCommand, WorkerCommandType
from app.application.camera_service import CommandPublisher
from app.application.errors import CameraNotFoundError, LineNotFoundError, UnprocessableError
from app.infrastructure.database.models import CameraModel, LineModel
from app.infrastructure.database.repositories.lines import LineRepository
from app.schemas.lines import LineRead

logger = logging.getLogger(__name__)
MAX_LINES_PER_CAMERA = 16


def read_line(row: LineModel) -> LineRead:
    return LineRead(
        id=row.id,
        camera_id=row.camera_id,
        name=row.name,
        p1={"x": row.p1_x, "y": row.p1_y},
        p2={"x": row.p2_x, "y": row.p2_y},
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class LineService:
    def __init__(
        self, repository: LineRepository, commands: CommandPublisher, clock: Clock
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

    async def list(self, camera_id: UUID) -> list[LineRead]:
        await self._require_camera(camera_id)
        return [read_line(z) for z in await self._repo.list(camera_id)]

    async def save(self, camera_id: UUID, body: LineShape, line_id: UUID | None = None) -> LineRead:
        await self._require_camera(camera_id, lock=True)
        now = self._clock.now()
        if line_id is None:
            if len(await self._repo.list(camera_id)) >= MAX_LINES_PER_CAMERA:
                raise UnprocessableError("At most 16 lines per camera")
            row = LineModel(id=uuid4(), camera_id=camera_id, created_at=now)
            self._repo.session.add(row)
        else:
            found = await self._repo.get(camera_id, line_id)
            if found is None:
                raise LineNotFoundError
            row = found
        row.name, row.enabled, row.updated_at = body.name, body.enabled, now
        row.p1_x, row.p1_y = body.p1.x, body.p1.y
        row.p2_x, row.p2_y = body.p2.x, body.p2.y
        result = read_line(row)
        await self._repo.session.commit()
        await self._notify(camera_id)
        return result

    async def delete(self, camera_id: UUID, line_id: UUID) -> None:
        await self._require_camera(camera_id, lock=True)
        row = await self._repo.get(camera_id, line_id)
        if row is None:
            raise LineNotFoundError
        await self._repo.session.delete(row)
        await self._repo.session.commit()
        await self._notify(camera_id)

    async def _notify(self, camera_id: UUID) -> None:
        try:
            await self._commands.publish(
                WorkerCommand(type=WorkerCommandType.CAMERA_CHANGED, camera_id=camera_id)
            )
        except RedisError:
            logger.exception("line notification not delivered", extra={"camera_id": str(camera_id)})
