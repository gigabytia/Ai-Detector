"""Persistence access for camera-owned zones."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import ZoneModel


class ZoneRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, camera_id: UUID) -> list[ZoneModel]:
        return list(
            await self.session.scalars(
                select(ZoneModel)
                .where(ZoneModel.camera_id == camera_id)
                .order_by(ZoneModel.created_at, ZoneModel.id)
            )
        )

    async def get(self, camera_id: UUID, zone_id: UUID) -> ZoneModel | None:
        return await self.session.scalar(
            select(ZoneModel).where(ZoneModel.id == zone_id, ZoneModel.camera_id == camera_id)
        )
