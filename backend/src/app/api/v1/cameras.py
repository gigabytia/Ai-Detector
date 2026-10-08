"""Camera CRUD and desired-state commands (start/stop/restart)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_camera_service
from app.api.errors import ErrorResponse
from app.application.camera_service import CameraChanges, CameraService
from app.schemas.cameras import CameraCreate, CameraRead, CameraUpdate

router = APIRouter(prefix="/cameras", tags=["cameras"])
Service = Annotated[CameraService, Depends(get_camera_service)]
# Any: FastAPI types the OpenAPI "responses" mapping as dict[int | str, dict[str, Any]].
NOT_FOUND: dict[int | str, dict[str, Any]] = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}


@router.get("", response_model=list[CameraRead])
async def list_cameras(service: Service) -> list[CameraRead]:
    return [CameraRead.from_view(view) for view in await service.list_cameras()]


@router.post(
    "",
    response_model=CameraRead,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"model": ErrorResponse}},
)
async def create_camera(body: CameraCreate, service: Service) -> CameraRead:
    view = await service.create_camera(body.name, body.source_type, body.source_url, body.enabled)
    return CameraRead.from_view(view)


@router.get("/{camera_id}", response_model=CameraRead, responses=NOT_FOUND)
async def get_camera(camera_id: uuid.UUID, service: Service) -> CameraRead:
    return CameraRead.from_view(await service.get_camera(camera_id))


@router.patch(
    "/{camera_id}",
    response_model=CameraRead,
    responses={**NOT_FOUND, status.HTTP_409_CONFLICT: {"model": ErrorResponse}},
)
async def update_camera(camera_id: uuid.UUID, body: CameraUpdate, service: Service) -> CameraRead:
    changes = CameraChanges(
        name=body.name, source_type=body.source_type, source_url=body.source_url
    )
    return CameraRead.from_view(await service.update_camera(camera_id, changes))


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
async def delete_camera(camera_id: uuid.UUID, service: Service) -> Response:
    await service.delete_camera(camera_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{camera_id}/start", response_model=CameraRead, responses=NOT_FOUND)
async def start_camera(camera_id: uuid.UUID, service: Service) -> CameraRead:
    return CameraRead.from_view(await service.set_enabled(camera_id, enabled=True))


@router.post("/{camera_id}/stop", response_model=CameraRead, responses=NOT_FOUND)
async def stop_camera(camera_id: uuid.UUID, service: Service) -> CameraRead:
    return CameraRead.from_view(await service.set_enabled(camera_id, enabled=False))


@router.post("/{camera_id}/restart", response_model=CameraRead, responses=NOT_FOUND)
async def restart_camera(camera_id: uuid.UUID, service: Service) -> CameraRead:
    return CameraRead.from_view(await service.restart(camera_id))
