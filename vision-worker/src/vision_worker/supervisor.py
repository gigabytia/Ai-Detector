"""Owns worker components and their start/stop order. Contains no business rules (§135)."""

import asyncio
import logging
from collections.abc import Callable, Coroutine

import httpx
from redis.asyncio import Redis

from vision_worker.cameras.manager import CameraManager
from vision_worker.messaging.analytics import AnalyticsPublisher
from vision_worker.messaging.camera_status import CameraStatusPublisher
from vision_worker.messaging.commands import CommandListener
from vision_worker.messaging.events import EventPublisher
from vision_worker.messaging.heartbeat import HeartbeatPublisher
from vision_worker.pipeline.preview import PreviewHub
from vision_worker.pipeline.scheduler import InferenceScheduler
from vision_worker.pipeline.telemetry import TelemetryHub
from vision_worker.storage.snapshot_writer import SnapshotWriter

logger = logging.getLogger(__name__)

Loop = Callable[[asyncio.Event], Coroutine[object, object, None]]


class Supervisor:
    def __init__(
        self,
        redis: Redis,
        api_http: httpx.AsyncClient,
        heartbeat: HeartbeatPublisher,
        manager: CameraManager,
        commands: CommandListener,
        camera_status: CameraStatusPublisher,
        scheduler: InferenceScheduler,
        preview: PreviewHub,
        detector_info: dict[str, str],
        events: EventPublisher | None = None,
        telemetry: TelemetryHub | None = None,
        snapshots: SnapshotWriter | None = None,
        analytics: AnalyticsPublisher | None = None,
    ) -> None:
        self.analytics = analytics
        self._analytics_task: asyncio.Task[None] | None = None
        self.snapshots = snapshots
        self._delivery_stop = asyncio.Event()
        self._event_task: asyncio.Task[None] | None = None
        self.events = events
        self.telemetry = telemetry or TelemetryHub()
        self.scheduler = scheduler
        self.preview = preview
        self.detector_info = detector_info
        self._redis = redis
        self._api_http = api_http
        self._heartbeat = heartbeat
        self._manager = manager
        self._commands = commands
        self._camera_status = camera_status
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def heartbeat(self) -> HeartbeatPublisher:
        return self._heartbeat

    @property
    def manager(self) -> CameraManager:
        return self._manager

    async def start(self) -> None:
        self._stop.clear()
        self._delivery_stop.clear()
        loops: dict[str, Loop] = {
            "inference": self.scheduler.run,
            "heartbeat": self._heartbeat.run,
            "commands": self._commands.run,
            "camera-status": self._camera_status.run,
        }
        if self.events is not None:
            self._event_task = asyncio.create_task(
                self.events.run(self._delivery_stop), name="events"
            )
            self._event_task.add_done_callback(_report_crash)
            self._event_task.add_done_callback(self._event_delivery_finished)
        if self.analytics is not None:
            self._analytics_task = asyncio.create_task(
                self.analytics.run(self._delivery_stop), name="analytics"
            )
            self._analytics_task.add_done_callback(_report_crash)
            self._analytics_task.add_done_callback(self._analytics_finished)
        for name, loop in loops.items():
            task = asyncio.create_task(loop(self._stop), name=name)
            task.add_done_callback(_report_crash)
            self._tasks.append(task)
        logger.info("worker started")

    def _analytics_finished(self, task: asyncio.Task[None]) -> None:
        if not self._delivery_stop.is_set() and self.analytics is not None:
            self.analytics.healthy = False

    def _event_delivery_finished(self, task: asyncio.Task[None]) -> None:
        if not self._delivery_stop.is_set() and self.events is not None:
            self.events.healthy = False

    async def stop(self) -> None:
        """Graceful shutdown: stop commands, stop cameras, withdraw status, close clients."""
        self._stop.set()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self.snapshots is not None:
            await self.snapshots.close()
        self._delivery_stop.set()
        if self._event_task is not None:
            await asyncio.gather(self._event_task, return_exceptions=True)
            self._event_task = None
        if self._analytics_task is not None:
            await asyncio.gather(self._analytics_task, return_exceptions=True)
            self._analytics_task = None
        await self._manager.stop_all()
        await self.preview.close()
        await self.telemetry.close()
        await self._camera_status.publish_once()  # deletes status keys of stopped cameras
        await self._heartbeat.withdraw()
        await self._api_http.aclose()
        await self._redis.aclose()
        logger.info("worker stopped")


def _report_crash(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and (exc := task.exception()) is not None:
        logger.error("worker loop crashed", extra={"loop": task.get_name()}, exc_info=exc)
