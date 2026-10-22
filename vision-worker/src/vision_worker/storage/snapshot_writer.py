"""Event-triggered full-frame JPEG, off the inference executor, bounded memory.

A storage/codec/queue failure publishes the alarm without a snapshot. Each event
is offered exactly once; completed metadata stays in the existing Redis outbox.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid5

import cv2

from ai_detector_core.events.domain import DomainEvent
from ai_detector_core.events.transport import EventMessage, SnapshotMetadata
from ai_detector_core.storage.snapshots import SnapshotStorage, snapshot_key
from vision_worker.cameras.frame import Frame
from vision_worker.messaging.events import EventPublisher

logger = logging.getLogger(__name__)


class SnapshotWriter:
    def __init__(
        self,
        storage: SnapshotStorage,
        events: EventPublisher,
        capacity: int = 32,
        max_retained_bytes: int = 128 * 1024**2,
    ) -> None:
        self.storage = storage
        self.events = events
        self.capacity = capacity
        self.max_retained_bytes = max_retained_bytes
        self.retained_bytes = 0
        self.results = {"disabled": 0, "busy": 0, "failed": 0, "written": 0}
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="snapshot")
        self._tasks: set[asyncio.Task[None]] = set()
        self._closed = False

    @property
    def pending_jobs(self) -> int:
        return len(self._tasks)

    def offer(self, event: DomainEvent, frame: Frame, enabled: bool) -> None:
        if (
            not enabled
            or self._closed
            or len(self._tasks) >= self.capacity
            or self.retained_bytes + frame.image.nbytes > self.max_retained_bytes
        ):
            self.results["busy" if enabled else "disabled"] += 1
            if enabled:
                logger.warning(
                    "snapshot skipped: writer closed or busy", extra={"event_id": str(event.id)}
                )
            self.events.offer(event)
            return
        self.retained_bytes += frame.image.nbytes
        task = asyncio.create_task(self._prepare(event, frame), name=f"snapshot-{event.id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _write(self, event: DomainEvent, frame: Frame) -> SnapshotMetadata:
        ok, encoded = cv2.imencode(".jpg", frame.image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise ValueError("Snapshot JPEG encoding failed")
        data = encoded.tobytes()
        snapshot_id = uuid5(event.id, "snapshot")
        key = snapshot_key(event.camera_id, event.occurred_at, snapshot_id)
        metadata = SnapshotMetadata(
            id=snapshot_id,
            event_id=event.id,
            storage_key=key,
            width=frame.size[0],
            height=frame.size[1],
            size_bytes=len(data),
            created_at=datetime.now(UTC),
        )
        self.storage.put(key, data)
        return metadata

    async def _prepare(self, event: DomainEvent, frame: Frame) -> None:
        try:
            metadata = await asyncio.get_running_loop().run_in_executor(
                self._pool, self._write, event, frame
            )
            outgoing: DomainEvent = EventMessage(**event.model_dump(), snapshot=metadata)
            self.results["written"] += 1
        except Exception:
            self.results["failed"] += 1
            logger.exception(
                "snapshot failed; publishing event without image", extra={"event_id": str(event.id)}
            )
            outgoing = event
        finally:
            self.retained_bytes -= frame.image.nbytes
        self.events.offer(outgoing)

    async def close(self) -> None:
        self._closed = True
        await asyncio.gather(*tuple(self._tasks))
        self._pool.shutdown(wait=True)
