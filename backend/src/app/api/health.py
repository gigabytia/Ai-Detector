"""Process health for orchestrators: /health/live and /health/ready."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_system_service
from app.application.system_service import SystemService
from app.schemas.system import DependencyStatusRead, LivenessRead, ReadinessRead

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessRead)
async def live() -> LivenessRead:
    return LivenessRead(status="alive")


@router.get(
    "/ready",
    response_model=ReadinessRead,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessRead}},
)
async def ready(
    response: Response, service: Annotated[SystemService, Depends(get_system_service)]
) -> ReadinessRead:
    dependencies = await service.check_dependencies()
    is_ready = all(item.ok for item in dependencies)
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessRead(
        status="ready" if is_ready else "not_ready",
        dependencies=[
            DependencyStatusRead(name=d.name, ok=d.ok, error=d.error) for d in dependencies
        ],
    )
