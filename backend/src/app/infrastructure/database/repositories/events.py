"""Event repository. Each caller owns its session and transaction."""

from __future__ import annotations

import builtins
from datetime import datetime
from uuid import UUID

from sqlalchemy import RowMapping, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.infrastructure.database.models import CameraModel, EventModel, SnapshotModel
from app.schemas.events import EventRead


def event_read(model: EventModel) -> EventRead:
    values = {
        field: getattr(model, field)
        for field in EventRead.model_fields
        if field
        not in {"metadata", "snapshot_id", "snapshot_url", "snapshot_width", "snapshot_height"}
    }
    snapshot = model.snapshot
    return EventRead.model_validate(
        {
            **values,
            "metadata": model.event_metadata,
            "snapshot_id": snapshot.id if snapshot else None,
            "snapshot_url": f"/api/v1/snapshots/{snapshot.id}" if snapshot else None,
            "snapshot_width": snapshot.width if snapshot else None,
            "snapshot_height": snapshot.height if snapshot else None,
        }
    )


def event_predicates(
    camera_id: UUID | None,
    status: str | None,
    event_type: str | None,
    start: datetime | None,
    end: datetime | None,
) -> list[ColumnElement[bool]]:
    terms: list[ColumnElement[bool]] = []
    if camera_id is not None:
        terms.append(EventModel.camera_id == camera_id)
    if status is not None:
        terms.append(EventModel.status == status)
    if event_type is not None:
        terms.append(EventModel.type == event_type)
    if start is not None:
        terms.append(EventModel.occurred_at >= start)
    if end is not None:
        terms.append(EventModel.occurred_at < end)
    return terms


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        limit: int,
        camera_id: UUID | None,
        status: str | None,
        before: tuple[datetime, UUID] | None,
        *,
        event_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[EventModel]:
        query = select(EventModel).where(
            *event_predicates(camera_id, status, event_type, start, end)
        )
        if before is not None:
            at, event_id = before
            query = query.where(
                or_(
                    EventModel.occurred_at < at,
                    and_(EventModel.occurred_at == at, EventModel.id < event_id),
                )
            )
        query = query.order_by(EventModel.occurred_at.desc(), EventModel.id.desc()).limit(limit)
        return list(await self.session.scalars(query))

    async def export_rows(
        self,
        limit: int,
        camera_id: UUID | None,
        status: str | None,
        event_type: str | None,
        start: datetime | None,
        end: datetime | None,
    ) -> builtins.list[RowMapping]:
        # One SELECT = one consistent DB snapshot. No ORM/snapshot N+1 and no storage keys.
        columns = [
            getattr(EventModel, name)
            for name in (
                "id",
                "occurred_at",
                "camera_id",
                "run_id",
                "track_id",
                "type",
                "severity",
                "status",
                "zone_id",
                "line_id",
                "detector_confidence",
                "event_confidence",
                "message",
                "note",
                "acknowledged_at",
                "false_positive_at",
            )
        ]
        query = (
            select(
                *columns,
                CameraModel.name.label("camera_name"),
                EventModel.event_metadata.label("metadata_json"),
                SnapshotModel.id.label("snapshot_id"),
            )
            .join(CameraModel, CameraModel.id == EventModel.camera_id)
            .outerjoin(SnapshotModel, SnapshotModel.event_id == EventModel.id)
            .where(*event_predicates(camera_id, status, event_type, start, end))
            .order_by(EventModel.occurred_at.desc(), EventModel.id.desc())
            .limit(limit)
        )
        from sqlalchemy import text

        await self.session.execute(text("SET LOCAL statement_timeout = '15000ms'"))
        return list((await self.session.execute(query)).mappings())

    async def get(self, event_id: UUID, lock: bool = False) -> EventModel | None:
        query = select(EventModel).where(EventModel.id == event_id)
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query)
