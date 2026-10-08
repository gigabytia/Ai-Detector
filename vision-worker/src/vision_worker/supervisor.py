"""Owns worker components and their start/stop order. Contains no business rules (§135)."""

import asyncio
import logging
from collections.abc import Callable, Coroutine

import httpx
from redis.asyncio import Redis

from vision_worker.cameras.manager import CameraManager
from vision_worker.messaging.camera_status import CameraStatusPublisher
from vision_worker.messaging.commands import CommandListener
from vision_worker.messaging.heartbeat import HeartbeatPublisher

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
    ) -> None:
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
        loops: dict[str, Loop] = {
            "heartbeat": self._heartbeat.run,
            "commands": self._commands.run,
            "camera-status": self._camera_status.run,
        }
        for name, loop in loops.items():
            task = asyncio.create_task(loop(self._stop), name=name)
            task.add_done_callback(_report_crash)
            self._tasks.append(task)
        logger.info("worker started")

    async def stop(self) -> None:
        """Graceful shutdown: stop commands, stop cameras, withdraw status, close clients."""
        self._stop.set()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self._manager.stop_all()
        await self._camera_status.publish_once()  # deletes status keys of stopped cameras
        await self._heartbeat.withdraw()
        await self._api_http.aclose()
        await self._redis.aclose()
        logger.info("worker stopped")


def _report_crash(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and (exc := task.exception()) is not None:
        logger.error("worker loop crashed", extra={"loop": task.get_name()}, exc_info=exc)
