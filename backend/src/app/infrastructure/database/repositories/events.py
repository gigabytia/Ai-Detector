"""Event repository. Each caller owns its session and transaction."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import EventModel
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


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        limit: int,
        camera_id: UUID | None,
        status: str | None,
        before: tuple[datetime, UUID] | None,
    ) -> list[EventModel]:
        query = select(EventModel)
        if camera_id is not None:
            query = query.where(EventModel.camera_id == camera_id)
        if status is not None:
            query = query.where(EventModel.status == status)
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

    async def get(self, event_id: UUID, lock: bool = False) -> EventModel | None:
        query = select(EventModel).where(EventModel.id == event_id)
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query)
