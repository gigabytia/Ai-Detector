"""System status for the operator UI: dependencies and connected vision workers."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_system_service
from app.application.system_service import SystemService
from app.schemas.system import DependencyStatusRead, SystemStatusRead, WorkerStatusRead

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatusRead)
async def get_system_status(
    service: Annotated[SystemService, Depends(get_system_service)],
) -> SystemStatusRead:
    result = await service.get_status()
    now = service.clock.now()
    return SystemStatusRead(
        status="ok" if result.ready and result.workers else "degraded",
        checked_at=now,
        dependencies=[
            DependencyStatusRead(name=d.name, ok=d.ok, error=d.error) for d in result.dependencies
        ],
        workers=[
            WorkerStatusRead(
                worker_id=w.worker_id,
                version=w.version,
                started_at=w.started_at,
                last_seen_at=w.sent_at,
                uptime_seconds=w.uptime_seconds(now),
            )
            for w in result.workers
        ],
    )
