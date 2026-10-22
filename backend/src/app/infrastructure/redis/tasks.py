"""Readiness guard for process-owned event delivery tasks."""

import asyncio
import logging

logger = logging.getLogger(__name__)


class EventTasksProbe:
    name = "event_delivery"

    def __init__(self, expected_count: int = 2, name: str = "event_delivery") -> None:
        self.expected_count = expected_count
        self.name = name
        self.tasks: list[asyncio.Task[None]] = []

    async def check(self) -> None:
        if len(self.tasks) != self.expected_count or any(task.done() for task in self.tasks):
            raise RuntimeError("Event delivery task stopped")


def report_task_failure(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and (exc := task.exception()) is not None:
        logger.error("event task crashed", extra={"task": task.get_name()}, exc_info=exc)
