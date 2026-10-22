"""Camera-scoped directed-line endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from ai_detector_core.lines.model import LineShape
from app.api.deps import get_line_service
from app.api.errors import ErrorResponse
from app.application.line_service import LineService
from app.schemas.lines import LineRead

router = APIRouter(
    prefix="/cameras/{camera_id}/lines", tags=["lines"], responses={404: {"model": ErrorResponse}}
)
Service = Annotated[LineService, Depends(get_line_service)]


@router.get("", response_model=list[LineRead])
async def list_lines(camera_id: UUID, service: Service) -> list[LineRead]:
    return await service.list(camera_id)


@router.post("", response_model=LineRead, status_code=201)
async def create_line(camera_id: UUID, body: LineShape, service: Service) -> LineRead:
    return await service.save(camera_id, body)


@router.put("/{line_id}", response_model=LineRead)
async def replace_line(
    camera_id: UUID, line_id: UUID, body: LineShape, service: Service
) -> LineRead:
    return await service.save(camera_id, body, line_id)


@router.delete("/{line_id}", status_code=204)
async def delete_line(camera_id: UUID, line_id: UUID, service: Service) -> Response:
    await service.delete(camera_id, line_id)
    return Response(status_code=204)
