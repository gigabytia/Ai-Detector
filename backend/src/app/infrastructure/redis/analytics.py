"""Idempotent analytics sink; same commit-before-ACK/reclaim mechanics as alarms."""

import logging
from typing import cast

from pydantic import ValidationError
from sqlalchemy import Table, select
from sqlalchemy.dialects.postgresql import insert

from ai_detector_core.telemetry.analytics import (
    ANALYTICS_ADAPTER,
    ANALYTICS_DEAD,
    ANALYTICS_GROUP,
    ANALYTICS_STREAM,
    CameraSample,
)
from app.infrastructure.database.models import CameraModel, CameraSampleModel, TrackSessionModel
from app.infrastructure.redis.ingest import EventIngest

logger = logging.getLogger(__name__)


class AnalyticsIngest(EventIngest):
    stream = ANALYTICS_STREAM
    group = ANALYTICS_GROUP
    dead = ANALYTICS_DEAD

    async def process(self, messages: list[tuple[bytes, dict[bytes, bytes]]]) -> None:
        valid = []
        dead = []
        for mid, fields in messages:
            try:
                raw = fields[b"data"]
                if len(raw) > 524288:
                    raise ValueError("Analytics message too large")
                valid.append(ANALYTICS_ADAPTER.validate_json(raw))
            except (KeyError, ValueError, ValidationError) as exc:
                dead.append((mid, type(exc).__name__))
        async with self.sessions() as session, session.begin():
            cameras = set(
                await session.scalars(
                    select(CameraModel.id).where(CameraModel.id.in_({v.camera_id for v in valid}))
                )
            )
            for message in valid:
                if message.camera_id not in cameras:
                    logger.warning("analytics references missing camera")
                    continue
                row = message.model_dump(exclude={"kind", "version"})
                model: type[CameraSampleModel] | type[TrackSessionModel]
                if isinstance(message, CameraSample):
                    model = CameraSampleModel
                else:
                    model = TrackSessionModel
                    row["segments"] = [s.model_dump(mode="json") for s in message.segments]
                await session.execute(
                    insert(cast(Table, model.__table__)).values(row).on_conflict_do_nothing()
                )
        async with self.redis.pipeline(transaction=True) as pipe:
            for mid, reason in dead:
                pipe.xadd(self.dead, {"message_id": mid, "reason": reason}, maxlen=1000)
                logger.warning("invalid analytics message", extra={"reason": reason})
            ids = [m for m, _ in messages]
            if ids:
                pipe.xack(self.stream, self.group, *ids)
                pipe.xdel(self.stream, *ids)
            await pipe.execute()
