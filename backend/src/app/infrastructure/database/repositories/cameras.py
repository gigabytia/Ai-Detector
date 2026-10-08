"""CameraRepository: persistence of cameras. Deleted cameras are invisible here."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.errors import CameraNameConflictError
from app.infrastructure.database.models import CameraModel


class CameraRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> Sequence[CameraModel]:
        result = await self._session.scalars(
            select(CameraModel).where(CameraModel.deleted_at.is_(None)).order_by(CameraModel.name)
        )
        return result.all()

    async def list_enabled(self) -> Sequence[CameraModel]:
        result = await self._session.scalars(
            select(CameraModel)
            .where(CameraModel.deleted_at.is_(None), CameraModel.enabled.is_(True))
            .order_by(CameraModel.created_at)
        )
        return result.all()

    async def get_active(self, camera_id: uuid.UUID) -> CameraModel | None:
        return await self._session.scalar(
            select(CameraModel).where(CameraModel.id == camera_id, CameraModel.deleted_at.is_(None))
        )

    async def count_active(self) -> int:
        count = await self._session.scalar(
            select(func.count()).select_from(CameraModel).where(CameraModel.deleted_at.is_(None))
        )
        return int(count or 0)

    async def add(self, camera: CameraModel) -> None:
        self._session.add(camera)
        await self._flush()

    async def save(self, camera: CameraModel, now: datetime) -> None:
        camera.updated_at = now
        await self._flush()

    async def commit(self) -> None:
        await self._session.commit()

    async def _flush(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if "uq_cameras_name_active" in str(exc.orig):
                raise CameraNameConflictError from exc
            raise
