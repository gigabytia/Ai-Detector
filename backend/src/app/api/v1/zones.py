"""Camera-scoped danger-zone endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from ai_detector_core.zones.model import ZoneShape
from app.api.deps import get_zone_service
from app.api.errors import ErrorResponse
from app.application.zone_service import ZoneService
from app.schemas.zones import ZoneRead

router = APIRouter(
    prefix="/cameras/{camera_id}/zones", tags=["zones"], responses={404: {"model": ErrorResponse}}
)
Service = Annotated[ZoneService, Depends(get_zone_service)]


@router.get("", response_model=list[ZoneRead])
async def list_zones(camera_id: UUID, service: Service) -> list[ZoneRead]:
    return await service.list(camera_id)


@router.post("", response_model=ZoneRead, status_code=201)
async def create_zone(camera_id: UUID, body: ZoneShape, service: Service) -> ZoneRead:
    return await service.save(camera_id, body)


@router.put("/{zone_id}", response_model=ZoneRead)
async def replace_zone(
    camera_id: UUID, zone_id: UUID, body: ZoneShape, service: Service
) -> ZoneRead:
    return await service.save(camera_id, body, zone_id)


@router.delete("/{zone_id}", status_code=204)
async def delete_zone(camera_id: UUID, zone_id: UUID, service: Service) -> Response:
    await service.delete(camera_id, zone_id)
    return Response(status_code=204)
