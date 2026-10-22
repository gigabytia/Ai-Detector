"""Selected-camera JSON telemetry, separate from JPEG preview. Latest-only."""

import asyncio
import json
import time
from uuid import UUID

from ai_detector_core.people.track import PersonState
from vision_worker.pipeline.results import DetectionResult


class TelemetryHub:
    def __init__(self) -> None:
        self._subscribers: dict[UUID, set[asyncio.Queue[str]]] = {}
        self._last: dict[UUID, float] = {}

    def subscribe(self, camera_id: UUID) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        self._subscribers.setdefault(camera_id, set()).add(queue)
        return queue

    def unsubscribe(self, camera_id: UUID, queue: asyncio.Queue[str]) -> None:
        subscribers = self._subscribers.get(camera_id, set())
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(camera_id, None)
            self._last.pop(camera_id, None)

    def offer(self, result: DetectionResult) -> None:
        subscribers = self._subscribers.get(result.camera_id)
        now = time.monotonic()
        if not subscribers or now - self._last.get(result.camera_id, 0) < 0.2:
            return
        self._last[result.camera_id] = now
        packet = json.dumps(
            {
                "version": 1,
                "camera_id": str(result.camera_id),
                "run_id": str(result.run_id),
                "frame_id": result.frame.frame_id,
                "captured_at": result.frame.captured_at.isoformat(),
                "source_ts_ms": result.frame.source_ts_ms,
                "inference_ms": result.inference_ms,
                "persons": len(result.detections),
                "persons_in_zone": sum(
                    t.state == PersonState.IN_DANGER_ZONE for t in result.tracks
                ),
                "tracks": [
                    {
                        "track_id": t.track_id,
                        "state": t.state.value,
                        "confidence": t.confidence,
                        "bbox": [
                            t.bbox[0] / result.frame.size[0],
                            t.bbox[1] / result.frame.size[1],
                            t.bbox[2] / result.frame.size[0],
                            t.bbox[3] / result.frame.size[1],
                        ],
                    }
                    for t in result.tracks
                ],
            }
        )
        for queue in subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(packet)

    async def close(self) -> None:
        self._subscribers.clear()
        self._last.clear()
