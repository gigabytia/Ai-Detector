"""Dashboard policy: bounded windows, persisted MVCC data, optional live status."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from ai_detector_core.ports.clock import Clock
from app.application.camera_service import CameraStatusReader
from app.application.errors import ServiceUnavailableError, UnprocessableError
from app.infrastructure.database.repositories.analytics import AnalyticsRepository
from app.schemas.analytics import Dashboard, TrackPage

logger = logging.getLogger(__name__)


class AnalyticsService:
    def __init__(
        self, repository: AnalyticsRepository, statuses: CameraStatusReader, clock: Clock
    ) -> None:
        self.repository, self.statuses, self.clock = repository, statuses, clock

    def window(self, start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
        finish = end if end is not None else self.clock.now()
        begin = start if start is not None else finish - timedelta(hours=24)
        if begin >= finish or finish - begin > timedelta(days=31):
            raise UnprocessableError("Choose an ordered period up to 31 days")
        return begin.astimezone(UTC), finish.astimezone(UTC)

    async def dashboard(
        self, start: datetime | None, end: datetime | None, camera_id: UUID | None
    ) -> Dashboard:
        begin, finish = self.window(start, end)
        try:
            result = await self.repository.dashboard(begin, finish, camera_id, self.clock.now())
        except (SQLAlchemyError, OSError) as exc:
            raise ServiceUnavailableError("Analytics temporarily unavailable") from exc
        try:
            runtime = await self.statuses.get_many(
                [c.camera_id for c in result.by_camera if not c.archived]
            )
            result.active_cameras = sum(
                s.status.value in ("RUNNING", "DEGRADED") for s in runtime.values()
            )
        except (RedisError, OSError):
            logger.warning("analytics runtime camera count unavailable", exc_info=True)
        return result

    async def tracks(
        self,
        start: datetime | None,
        end: datetime | None,
        camera_id: UUID | None,
        limit: int,
        cursor: str | None,
    ) -> TrackPage:
        begin, finish = self.window(start, end)
        try:
            return await self.repository.tracks(begin, finish, camera_id, limit, cursor)
        except (SQLAlchemyError, OSError) as exc:
            raise ServiceUnavailableError("Track history temporarily unavailable") from exc
