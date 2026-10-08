"""Listens to worker commands and keeps the CameraManager in sync with the desired state.

Commands are only notifications. After every (re)subscription the listener does a full
reconcile, so commands missed while Redis or the API were down are not lost (ADR-004).
"""

import asyncio
import logging

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from ai_detector_core.telemetry.commands import WorkerCommand, WorkerCommandType
from ai_detector_core.telemetry.redis_keys import WORKER_COMMANDS_CHANNEL
from vision_worker.cameras.manager import CameraManager
from vision_worker.cameras.reconnect import Backoff, BackoffPolicy
from vision_worker.cameras.spec_client import CameraSpecClient, SpecUnavailableError

logger = logging.getLogger(__name__)

POLL_TIMEOUT_SECONDS = 1.0


class CommandListener:
    def __init__(
        self,
        redis: Redis,
        specs: CameraSpecClient,
        manager: CameraManager,
        retry: BackoffPolicy,
    ) -> None:
        self._redis = redis
        self._specs = specs
        self._manager = manager
        self._retry = Backoff(retry)
        self._needs_full_reconcile = True

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self._listen(stop)
            except RedisError:
                logger.exception("command channel lost, will resubscribe")
                self._needs_full_reconcile = True
            if not stop.is_set():
                await _sleep_or_stop(stop, self._retry.next_delay())

    async def _listen(self, stop: asyncio.Event) -> None:
        async with self._redis.pubsub() as pubsub:
            await pubsub.subscribe(WORKER_COMMANDS_CHANNEL)
            self._retry.reset()
            while not stop.is_set():
                if self._needs_full_reconcile:
                    await self._full_reconcile()
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=POLL_TIMEOUT_SECONDS
                )
                if message is not None:
                    await self._handle(message["data"])

    async def _full_reconcile(self) -> None:
        try:
            specs = await self._specs.list_enabled()
        except SpecUnavailableError:
            logger.exception("cannot load cameras from API; keeping current sessions")
            return  # retried on the next poll iteration
        await self._manager.reconcile(specs)
        self._needs_full_reconcile = False
        logger.info("cameras reconciled", extra={"cameras": len(specs)})

    async def _handle(self, raw: bytes | str) -> None:
        try:
            command = WorkerCommand.model_validate_json(raw)
        except ValidationError:
            logger.exception("invalid worker command ignored")
            return
        try:
            spec = await self._specs.get(command.camera_id)
        except SpecUnavailableError:
            logger.exception("cannot load camera spec", extra={"camera_id": str(command.camera_id)})
            self._needs_full_reconcile = True
            return
        if command.type is WorkerCommandType.CAMERA_RESTART:
            await self._manager.restart(command.camera_id, spec)
        else:
            await self._manager.apply(command.camera_id, spec)


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        return
