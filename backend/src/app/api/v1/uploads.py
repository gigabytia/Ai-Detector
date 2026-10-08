"""Video upload for file cameras. Files get generated names (ADR-012)."""

from collections.abc import AsyncIterator

from fastapi import APIRouter, UploadFile, status

from ai_detector_core.cameras.source import UPLOAD_SCHEME
from app.api.deps import Resources
from app.api.errors import ErrorResponse
from app.schemas.uploads import UploadRead

router = APIRouter(prefix="/uploads", tags=["uploads"])
CHUNK_SIZE = 1024 * 1024


async def _chunks(file: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await file.read(CHUNK_SIZE):
        yield chunk


@router.post(
    "",
    response_model=UploadRead,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorResponse}},
)
async def upload_video(file: UploadFile, resources: Resources) -> UploadRead:
    original = file.filename or ""
    ref, size = await resources.uploads.save(original, _chunks(file))
    return UploadRead(
        file_ref=ref, source_url=f"{UPLOAD_SCHEME}{ref}", size_bytes=size, original_name=original
    )
