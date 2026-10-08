"""Worker HTTP app: liveness, readiness and per-camera runtime status."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Response, status
from pydantic import AwareDatetime, BaseModel

from ai_detector_core.cameras.status import CameraRuntimeStatus
from vision_worker.supervisor import Supervisor


class WorkerLivenessRead(BaseModel):
    status: Literal["alive"]


class WorkerReadinessRead(BaseModel):
    status: Literal["ready", "not_ready"]
    redis_ok: bool
    last_heartbeat_at: AwareDatetime | None


class WorkerStatusRead(BaseModel):
    cameras: list[CameraRuntimeStatus]


def create_http_app(supervisor: Supervisor) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await supervisor.start()
        try:
            yield
        finally:
            await supervisor.stop()

    app = FastAPI(title="AI Detector Vision Worker", lifespan=lifespan)

    @app.get("/health/live", response_model=WorkerLivenessRead)
    async def live() -> WorkerLivenessRead:
        return WorkerLivenessRead(status="alive")

    @app.get("/health/ready", response_model=WorkerReadinessRead)
    async def ready(response: Response) -> WorkerReadinessRead:
        heartbeat = supervisor.heartbeat
        if not heartbeat.redis_ok:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return WorkerReadinessRead(
            status="ready" if heartbeat.redis_ok else "not_ready",
            redis_ok=heartbeat.redis_ok,
            last_heartbeat_at=heartbeat.last_published_at,
        )

    @app.get("/status", response_model=WorkerStatusRead)
    async def worker_status() -> WorkerStatusRead:
        return WorkerStatusRead(cameras=[s.status() for s in supervisor.manager.sessions])

    return app
