"""Event application service: history, status transitions and audit."""

import asyncio
import base64
import json
import logging
from contextlib import aclosing
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from ai_detector_core.ports.clock import Clock
from ai_detector_core.telemetry.event_bus import EVENTS_UPDATES, pending_event_key
from app.application.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableError,
)
from app.application.event_export import MAX_EXPORT_ROWS, CsvExportBuffer
from app.infrastructure.database.repositories.events import EventRepository, event_read
from app.schemas.events import EventPage, EventRead, EventUpdate

logger = logging.getLogger(__name__)


def decode_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    try:
        at, event_id = json.loads(base64.urlsafe_b64decode(cursor))
        if not isinstance(at, str) or not isinstance(event_id, str):
            raise ValueError("cursor components must be strings")
        timestamp = datetime.fromisoformat(at)
        if timestamp.tzinfo is None:
            raise ValueError("timezone required")
        return timestamp, UUID(event_id)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise UnprocessableError("Invalid event cursor") from exc


class EventService:
    def __init__(
        self,
        repository: EventRepository,
        redis: Redis,
        clock: Clock,
        export_slots: asyncio.Semaphore,
    ) -> None:
        self.repository = repository
        self.redis = redis
        self.clock = clock
        self.export_slots = export_slots

    @staticmethod
    def window(
        start: datetime | None, end: datetime | None
    ) -> tuple[datetime | None, datetime | None]:
        if start is not None and end is not None and start >= end:
            raise UnprocessableError("Choose an ordered event period")
        return start.astimezone(UTC) if start else None, end.astimezone(UTC) if end else None

    async def list(
        self,
        limit: int,
        camera_id: UUID | None,
        status: str | None,
        cursor: str | None,
        *,
        event_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> EventPage:
        start, end = self.window(start, end)
        before = decode_cursor(cursor)
        try:
            rows = await self.repository.list(
                limit + 1, camera_id, status, before, event_type=event_type, start=start, end=end
            )
        except (SQLAlchemyError, OSError) as exc:
            raise ServiceUnavailableError("Event history temporarily unavailable") from exc
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = base64.urlsafe_b64encode(
                json.dumps([last.occurred_at.isoformat(), str(last.id)]).encode()
            ).decode()
        return EventPage(items=[event_read(row) for row in rows[:limit]], next_cursor=next_cursor)

    async def export(
        self,
        camera_id: UUID | None,
        status: str | None,
        event_type: str | None,
        start: datetime | None,
        end: datetime | None,
    ) -> bytes:
        start, end = self.window(start, end)
        try:
            await asyncio.wait_for(self.export_slots.acquire(), timeout=0.05)
        except TimeoutError as exc:
            raise ServiceUnavailableError("CSV export busy; retry later") from exc
        try:
            buffer = CsvExportBuffer()
            rows = await self.repository.export_rows(
                MAX_EXPORT_ROWS + 1, camera_id, status, event_type, start, end
            )
            async with aclosing(rows):
                async for batch in rows:
                    await asyncio.to_thread(buffer.extend, batch)
            return buffer.finish()
        except (SQLAlchemyError, OSError) as exc:
            raise ServiceUnavailableError("CSV export temporarily unavailable") from exc
        finally:
            self.export_slots.release()

    async def get(self, event_id: UUID) -> EventRead:
        try:
            model = await self.repository.get(event_id)
        except (SQLAlchemyError, OSError) as exc:
            raise ServiceUnavailableError("Event history temporarily unavailable") from exc
        if model is None:
            raise NotFoundError("Event not found")
        return event_read(model)

    async def _not_persisted(self, event_id: UUID) -> None:
        try:
            published = await self.redis.exists(pending_event_key(event_id))
        except RedisError as exc:
            raise ServiceUnavailableError("Event delivery temporarily unavailable") from exc
        if published:
            error = ConflictError("Event not persisted yet; retry later")
            error.code = "EVENT_NOT_PERSISTED_YET"
            raise error

    async def update(self, event_id: UUID, body: EventUpdate) -> EventRead:
        session = self.repository.session
        try:
            model = await self.repository.get(event_id, lock=True)
        except (SQLAlchemyError, OSError) as exc:
            await self._not_persisted(event_id)
            raise ServiceUnavailableError("Event history temporarily unavailable") from exc
        if model is None:
            await self._not_persisted(event_id)
            raise NotFoundError("Event not found")
        if body.status is not None and model.status not in ("NEW", body.status):
            error = ConflictError("Event status is final")
            error.code = "EVENT_STATUS_CONFLICT"
            raise error
        now = self.clock.now()
        if body.status is not None and model.status == "NEW":
            model.status = body.status
            if body.status == "ACKNOWLEDGED":
                model.acknowledged_at = now
            else:
                model.false_positive_at = now
        if "note" in body.model_fields_set:
            model.note = body.note
        model.updated_at = now
        try:
            await session.commit()
            await session.refresh(model)
        except (SQLAlchemyError, OSError) as exc:
            raise ServiceUnavailableError(
                "Event update temporarily unavailable; reload and retry"
            ) from exc
        result = event_read(model)
        try:
            await self.redis.publish(EVENTS_UPDATES, result.model_dump_json())
        except RedisError:
            logger.warning("event status committed without live notification")
        return result
