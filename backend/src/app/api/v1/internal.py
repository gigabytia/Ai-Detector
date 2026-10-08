"""Internal endpoints for vision workers. Not part of the public contract (ADR-002)."""

import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from ai_detector_core.cameras.spec import CameraSpec
from app.api.deps import Resources, get_worker_spec_service
from app.application.worker_spec_service import WorkerSpecService


def require_worker_token(
    resources: Resources, authorization: Annotated[str | None, Header()] = None
) -> None:
    token = resources.settings.worker_api_token
    if token is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "WORKER_API_TOKEN is not set")
    expected = f"Bearer {token.get_secret_value()}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid worker token")


router = APIRouter(
    prefix="/internal/worker",
    tags=["internal"],
    include_in_schema=False,
    dependencies=[Depends(require_worker_token)],
)
Service = Annotated[WorkerSpecService, Depends(get_worker_spec_service)]


@router.get("/cameras", response_model=list[CameraSpec])
async def enabled_cameras(service: Service) -> list[CameraSpec]:
    return await service.enabled_specs()


@router.get("/cameras/{camera_id}", response_model=CameraSpec)
async def camera_spec(camera_id: uuid.UUID, service: Service) -> CameraSpec:
    return await service.spec(camera_id)
