"""Readiness guard for process-owned event delivery tasks."""

import asyncio
import logging

logger = logging.getLogger(__name__)


class EventTasksProbe:
    name = "event_delivery"

    def __init__(self) -> None:
        self.tasks: list[asyncio.Task[None]] = []

    async def check(self) -> None:
        if len(self.tasks) != 2 or any(task.done() for task in self.tasks):
            raise RuntimeError("Event delivery task stopped")


def report_task_failure(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and (exc := task.exception()) is not None:
        logger.error("event task crashed", extra={"task": task.get_name()}, exc_info=exc)
