"""Worker HTTP app: liveness, readiness and per-camera runtime status."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Literal, cast
from urllib.parse import urlsplit
from uuid import UUID

from anyio import CancelScope
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect, status
from pydantic import AwareDatetime, BaseModel

from ai_detector_core.cameras.status import CameraRuntimeStatus
from vision_worker.supervisor import Supervisor


class WorkerLivenessRead(BaseModel):
    status: Literal["alive"]


class WorkerReadinessRead(BaseModel):
    status: Literal["ready", "not_ready"]
    detector_loaded: bool
    detector: dict[str, str]
    analytics_ok: bool = True
    analytics_dropped: int = 0
    redis_ok: bool
    last_heartbeat_at: AwareDatetime | None


class WorkerStatusRead(BaseModel):
    cameras: list[CameraRuntimeStatus]


def create_http_app(supervisor: Supervisor, allowed_origins: list[str] | None = None) -> FastAPI:
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
        is_ready = (
            heartbeat.redis_ok
            and supervisor.scheduler.healthy
            and (supervisor.events is None or supervisor.events.healthy)
        )
        if not is_ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return WorkerReadinessRead(
            status="ready" if is_ready else "not_ready",
            analytics_ok=supervisor.analytics is None or supervisor.analytics.healthy,
            analytics_dropped=supervisor.analytics.dropped if supervisor.analytics else 0,
            detector_loaded=True,
            detector=supervisor.detector_info,
            redis_ok=heartbeat.redis_ok,
            last_heartbeat_at=heartbeat.last_published_at,
        )

    @app.get("/status", response_model=WorkerStatusRead)
    async def worker_status() -> WorkerStatusRead:
        return WorkerStatusRead(cameras=[s.status() for s in supervisor.manager.sessions])

    @app.websocket("/cameras/{camera_id}/telemetry")
    @app.websocket("/cameras/{camera_id}/preview")
    async def preview(websocket: WebSocket, camera_id: UUID) -> None:
        origin = websocket.headers.get("origin")
        same_origin = origin is not None and urlsplit(origin).netloc == websocket.headers.get(
            "host"
        )
        if origin is not None and not same_origin and origin not in (allowed_origins or []):
            await websocket.close(code=1008)
            return
        session = next((s for s in supervisor.manager.sessions if s.spec.id == camera_id), None)
        if session is None:
            await websocket.close(code=1008)
            return
        telemetry = websocket.url.path.endswith("/telemetry")
        queue: asyncio.Queue[str] | asyncio.Queue[bytes]
        if telemetry:
            queue = supervisor.telemetry.subscribe(camera_id)
        else:
            queue = supervisor.preview.subscribe(camera_id)
        tasks: list[asyncio.Task[None]] = []

        async def receive_disconnect() -> None:
            # Read disconnects even when the camera is reconnecting and no JPEG is produced.
            while (await websocket.receive())["type"] != "websocket.disconnect":
                pass

        async def send_frames() -> None:
            while True:
                current = next(
                    (s for s in supervisor.manager.sessions if s.spec.id == camera_id), None
                )
                if current is not session or current.state.value not in (
                    "STARTING",
                    "RUNNING",
                    "DEGRADED",
                    "RECONNECTING",
                ):
                    return
                try:
                    packet = await asyncio.wait_for(queue.get(), timeout=1)
                except TimeoutError:
                    continue
                if isinstance(packet, str):
                    await asyncio.wait_for(websocket.send_text(packet), timeout=2)
                else:
                    await asyncio.wait_for(websocket.send_bytes(cast(bytes, packet)), timeout=2)

        try:
            await websocket.accept()
            tasks = [asyncio.create_task(receive_disconnect()), asyncio.create_task(send_frames())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (WebSocketDisconnect, TimeoutError, RuntimeError, asyncio.CancelledError):
            pass
        finally:
            if telemetry:
                supervisor.telemetry.unsubscribe(camera_id, cast(asyncio.Queue[str], queue))
            else:
                supervisor.preview.unsubscribe(camera_id, cast(asyncio.Queue[bytes], queue))
            for task in tasks:
                task.cancel()
            # ASGI servers may cancel the connection while cleanup is awaiting child tasks.
            with CancelScope(shield=True):
                await asyncio.gather(*tasks, return_exceptions=True)
                with suppress(WebSocketDisconnect, RuntimeError):
                    await websocket.close(code=1000)

    return app
