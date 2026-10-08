"""Camera use cases: CRUD, desired running state, runtime status merge."""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from redis.exceptions import RedisError

from ai_detector_core.cameras.source import (
    InvalidSourceError,
    SourceType,
    upload_ref,
    validate_source_url,
)
from ai_detector_core.cameras.status import CameraRuntimeStatus
from ai_detector_core.ports.clock import Clock
from ai_detector_core.telemetry.commands import WorkerCommand, WorkerCommandType
from app.application.errors import (
    CameraLimitReachedError,
    CameraNotFoundError,
    InvalidCameraSourceError,
)
from app.infrastructure.database.models import CameraModel
from app.infrastructure.database.repositories.cameras import CameraRepository

logger = logging.getLogger(__name__)


class CommandPublisher(Protocol):
    async def publish(self, command: WorkerCommand) -> None: ...


class CameraStatusReader(Protocol):
    async def get_many(
        self, camera_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, CameraRuntimeStatus]: ...


class UploadIndex(Protocol):
    def exists(self, ref: str) -> bool: ...


@dataclass(frozen=True)
class CameraView:
    camera: CameraModel
    runtime: CameraRuntimeStatus | None


@dataclass(frozen=True)
class CameraChanges:
    name: str | None = None
    source_type: SourceType | None = None
    source_url: str | None = None


class CameraService:
    def __init__(
        self,
        repository: CameraRepository,
        commands: CommandPublisher,
        statuses: CameraStatusReader,
        uploads: UploadIndex,
        clock: Clock,
        max_cameras: int,
    ) -> None:
        self._repo = repository
        self._commands = commands
        self._statuses = statuses
        self._uploads = uploads
        self._clock = clock
        self._max_cameras = max_cameras

    async def list_cameras(self) -> list[CameraView]:
        cameras = await self._repo.list_active()
        runtime = await self._read_statuses([c.id for c in cameras])
        return [CameraView(camera=c, runtime=runtime.get(c.id)) for c in cameras]

    async def get_camera(self, camera_id: uuid.UUID) -> CameraView:
        camera = await self._require(camera_id)
        runtime = await self._read_statuses([camera.id])
        return CameraView(camera=camera, runtime=runtime.get(camera.id))

    async def create_camera(
        self, name: str, source_type: SourceType, source_url: str, enabled: bool
    ) -> CameraView:
        if await self._repo.count_active() >= self._max_cameras:
            raise CameraLimitReachedError(self._max_cameras)
        self._check_source(source_type, source_url)
        now = self._clock.now()
        camera = CameraModel(
            id=uuid.uuid4(),
            name=name,
            source_type=source_type.value,
            source_url=source_url,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        await self._repo.add(camera)
        await self._repo.commit()
        logger.info("camera created", extra={"camera_id": str(camera.id), "camera_name": name})
        if enabled:
            await self._notify(WorkerCommandType.CAMERA_CHANGED, camera.id)
        return CameraView(camera=camera, runtime=None)

    async def update_camera(self, camera_id: uuid.UUID, changes: CameraChanges) -> CameraView:
        camera = await self._require(camera_id)
        source_type = changes.source_type or SourceType(camera.source_type)
        source_url = changes.source_url or camera.source_url
        if changes.source_type is not None or changes.source_url is not None:
            self._check_source(source_type, source_url)
        if changes.name is not None:
            camera.name = changes.name
        camera.source_type = source_type.value
        camera.source_url = source_url
        await self._repo.save(camera, self._clock.now())
        await self._repo.commit()
        await self._notify(WorkerCommandType.CAMERA_CHANGED, camera.id)
        return await self.get_camera(camera.id)

    async def delete_camera(self, camera_id: uuid.UUID) -> None:
        camera = await self._require(camera_id)
        now = self._clock.now()
        camera.deleted_at = now
        camera.enabled = False
        await self._repo.save(camera, now)
        await self._repo.commit()
        logger.info("camera deleted", extra={"camera_id": str(camera.id)})
        await self._notify(WorkerCommandType.CAMERA_CHANGED, camera.id)

    async def set_enabled(self, camera_id: uuid.UUID, enabled: bool) -> CameraView:
        camera = await self._require(camera_id)
        if camera.enabled != enabled:
            camera.enabled = enabled
            await self._repo.save(camera, self._clock.now())
            await self._repo.commit()
        await self._notify(WorkerCommandType.CAMERA_CHANGED, camera.id)
        return await self.get_camera(camera.id)

    async def restart(self, camera_id: uuid.UUID) -> CameraView:
        camera = await self._require(camera_id)
        if not camera.enabled:
            camera.enabled = True
            await self._repo.save(camera, self._clock.now())
            await self._repo.commit()
        await self._notify(WorkerCommandType.CAMERA_RESTART, camera.id)
        return await self.get_camera(camera.id)

    async def _require(self, camera_id: uuid.UUID) -> CameraModel:
        camera = await self._repo.get_active(camera_id)
        if camera is None:
            raise CameraNotFoundError
        return camera

    def _check_source(self, source_type: SourceType, source_url: str) -> None:
        try:
            validate_source_url(source_type, source_url)
        except InvalidSourceError as exc:
            raise InvalidCameraSourceError(str(exc)) from exc
        if source_type is SourceType.FILE and not self._uploads.exists(upload_ref(source_url)):
            raise InvalidCameraSourceError("Uploaded file not found; upload it via /uploads first")

    async def _notify(self, command_type: WorkerCommandType, camera_id: uuid.UUID) -> None:
        # The desired state is already committed; a worker that missed the notification
        # catches up on its next full reconcile (after Redis reconnects), so this is not fatal.
        try:
            await self._commands.publish(WorkerCommand(type=command_type, camera_id=camera_id))
        except RedisError:
            logger.exception(
                "worker command not delivered",
                extra={"camera_id": str(camera_id), "command": command_type.value},
            )

    async def _read_statuses(
        self, camera_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, CameraRuntimeStatus]:
        try:
            return await self._statuses.get_many(camera_ids)
        except RedisError:
            logger.exception("camera status unavailable")
            return {}
