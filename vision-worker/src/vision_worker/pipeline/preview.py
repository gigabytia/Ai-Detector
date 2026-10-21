"""On-demand JPEG preview. One pending encode/camera and one queued packet/viewer."""

import asyncio
import json
import logging
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import cv2
import numpy as np

from vision_worker.pipeline.results import DetectionResult

logger = logging.getLogger(__name__)


def encode_packet(result: DetectionResult, max_width: int) -> bytes:
    frame = result.frame
    width, height = frame.size
    image = frame.image
    if width > max_width:
        image = cv2.resize(image, (max_width, max(1, round(height * max_width / width)))).astype(
            np.uint8
        )
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise ValueError("JPEG encoding failed")
    header = json.dumps(
        {
            "version": 1,
            "camera_id": str(result.camera_id),
            "run_id": str(result.run_id),
            "frame_id": frame.frame_id,
            "source_ts_ms": frame.source_ts_ms,
            "captured_at": frame.captured_at.isoformat(),
            "width": width,
            "height": height,
            "inference_ms": result.inference_ms,
            "tracks": [
                {
                    "track_id": t.track_id,
                    "bbox": [x1 / width, y1 / height, x2 / width, y2 / height],
                    "confidence": t.confidence,
                    "state": t.state.value,
                    "age": t.age,
                    "hits": t.hits,
                    "missed_frames": t.missed_frames,
                }
                for t in result.tracks
                for x1, y1, x2, y2 in [t.bbox]
            ],
            "detections": [
                {
                    "bbox": [x1 / width, y1 / height, x2 / width, y2 / height],
                    "confidence": d.confidence,
                }
                for d in result.detections
                for x1, y1, x2, y2 in [d.bbox]
            ],
        },
        separators=(",", ":"),
    ).encode()
    return struct.pack("!I", len(header)) + header + encoded.tobytes()


class PreviewHub:
    def __init__(self, fps: float = 5, max_width: int = 640) -> None:
        self._interval = 1 / fps
        self._width = max_width
        self._viewers: dict[UUID, set[asyncio.Queue[bytes]]] = {}
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._last: dict[UUID, float] = {}
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="preview")

    def subscribe(self, camera_id: UUID) -> asyncio.Queue[bytes]:
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
        self._viewers.setdefault(camera_id, set()).add(queue)
        return queue

    def unsubscribe(self, camera_id: UUID, queue: asyncio.Queue[bytes]) -> None:
        viewers = self._viewers.get(camera_id)
        if viewers is not None:
            viewers.discard(queue)
            if not viewers:
                self._viewers.pop(camera_id, None)
                self._last.pop(camera_id, None)

    def offer(self, result: DetectionResult) -> None:
        camera_id = result.camera_id
        now = time.monotonic()
        if not self._viewers.get(camera_id) or camera_id in self._tasks:
            return
        if now - self._last.get(camera_id, -float("inf")) < self._interval:
            return
        self._last[camera_id] = now
        self._tasks[camera_id] = asyncio.create_task(
            self._encode(result, set(self._viewers[camera_id]))
        )

    async def _encode(self, result: DetectionResult, recipients: set[asyncio.Queue[bytes]]) -> None:
        try:
            packet = await asyncio.get_running_loop().run_in_executor(
                self._pool, encode_packet, result, self._width
            )
            for queue in recipients & self._viewers.get(result.camera_id, set()):
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(packet)
        except Exception:
            logger.exception("preview encoding failed", extra={"camera_id": str(result.camera_id)})
        finally:
            self._tasks.pop(result.camera_id, None)

    async def close(self) -> None:
        await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)
        self._pool.shutdown(wait=True)
        self._viewers.clear()
        self._last.clear()
