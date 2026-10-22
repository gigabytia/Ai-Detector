"""Persistence access for camera-owned lines."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import LineModel


class LineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, camera_id: UUID) -> list[LineModel]:
        return list(
            await self.session.scalars(
                select(LineModel)
                .where(LineModel.camera_id == camera_id)
                .order_by(LineModel.created_at, LineModel.id)
            )
        )

    async def get(self, camera_id: UUID, line_id: UUID) -> LineModel | None:
        return await self.session.scalar(
            select(LineModel).where(LineModel.id == line_id, LineModel.camera_id == camera_id)
        )
