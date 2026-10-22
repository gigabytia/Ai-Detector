"""Read a private JPEG by metadata UUID, never by caller-supplied filesystem path."""

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ai_detector_core.storage.snapshots import LocalSnapshotStorage
from app.api.deps import Resources, Session
from app.api.errors import ErrorResponse
from app.application.errors import NotFoundError
from app.infrastructure.database.models import SnapshotModel


class SnapshotNotFoundError(NotFoundError):
    code = "SNAPSHOT_NOT_FOUND"


router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get(
    "/{snapshot_id}",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"image/jpeg": {"schema": {"type": "string", "format": "binary"}}}},
        404: {"model": ErrorResponse},
    },
)
async def get_snapshot(
    snapshot_id: UUID, resources: Resources, session: Session
) -> StreamingResponse:
    model = await session.get(SnapshotModel, snapshot_id)
    if model is None:
        raise SnapshotNotFoundError("Snapshot not found or expired")
    storage = LocalSnapshotStorage(resources.settings.snapshot_path)
    try:
        file = await asyncio.to_thread(storage.open, model.storage_key)
    except (OSError, ValueError) as exc:
        raise SnapshotNotFoundError("Snapshot file not available") from exc

    async def chunks() -> AsyncIterator[bytes]:
        try:
            while data := await asyncio.to_thread(file.read, 65536):
                yield data
        finally:
            file.close()

    return StreamingResponse(
        chunks(),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{snapshot_id}.jpg"',
        },
    )
