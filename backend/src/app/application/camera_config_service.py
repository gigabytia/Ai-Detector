"""Configuration overrides and effective settings; hot updates notify the worker."""

import logging
import uuid

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_detector_core.cameras.config import CameraConfig, CameraConfigOverrides, CameraConfigRead
from ai_detector_core.telemetry.commands import WorkerCommand, WorkerCommandType
from app.application.camera_service import CommandPublisher
from app.application.errors import CameraNotFoundError
from app.infrastructure.database.models import CameraConfigModel, CameraModel

logger = logging.getLogger(__name__)


def config_overrides(row: CameraConfigModel | None) -> CameraConfigOverrides:
    return CameraConfigOverrides(
        target_fps=row.target_fps if row else None,
        detection_confidence=row.detection_confidence if row else None,
    )


class CameraConfigService:
    def __init__(
        self, session: AsyncSession, commands: CommandPublisher, defaults: CameraConfig
    ) -> None:
        self._session = session
        self._commands = commands
        self._defaults = defaults

    async def _require(self, camera_id: uuid.UUID, *, lock: bool = False) -> None:
        statement = select(CameraModel).where(
            CameraModel.id == camera_id, CameraModel.deleted_at.is_(None)
        )
        if lock:
            statement = statement.with_for_update()
        if await self._session.scalar(statement) is None:
            raise CameraNotFoundError

    async def get(self, camera_id: uuid.UUID) -> CameraConfigRead:
        await self._require(camera_id)
        overrides = config_overrides(await self._session.get(CameraConfigModel, camera_id))
        return CameraConfigRead(
            overrides=overrides,
            defaults=self._defaults,
            effective=overrides.resolve(self._defaults),
        )

    async def replace(
        self, camera_id: uuid.UUID, overrides: CameraConfigOverrides
    ) -> CameraConfigRead:
        # Serialize simultaneous first writes by locking the parent row.
        await self._require(camera_id, lock=True)
        row = await self._session.get(CameraConfigModel, camera_id)
        if row is None:
            row = CameraConfigModel(camera_id=camera_id)
            self._session.add(row)
        row.target_fps = overrides.target_fps
        row.detection_confidence = overrides.detection_confidence
        await self._session.commit()
        try:
            await self._commands.publish(
                WorkerCommand(type=WorkerCommandType.CAMERA_CHANGED, camera_id=camera_id)
            )
        except RedisError:
            logger.exception(
                "camera config notification not delivered", extra={"camera_id": str(camera_id)}
            )
        return CameraConfigRead(
            overrides=overrides,
            defaults=self._defaults,
            effective=overrides.resolve(self._defaults),
        )
