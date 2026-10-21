"""Roboflow ByteTrack adapter. No library objects escape this boundary."""

from collections.abc import Sequence
from dataclasses import replace
from uuid import UUID

import numpy as np
from supervision import Detections
from trackers import ByteTrackTracker

from ai_detector_core.people.track import PersonState, PersonTrack
from vision_worker.cameras.frame import Frame
from vision_worker.inference.detector import PersonDetection


class ByteTrackPersonTracker:
    def __init__(
        self,
        camera_id: UUID,
        run_id: UUID,
        max_age: int = 25,
        match_iou: float = 0.5,
        activation_confidence: float = 0.25,
    ) -> None:
        self._camera_id = camera_id
        self._run_id = run_id
        self._max_age = max_age
        self._tracker = ByteTrackTracker(
            lost_track_buffer=max_age,
            frame_rate=30,  # Fixed-step mode: exactly one age tick per processed frame.
            minimum_consecutive_frames=1,
            minimum_iou_threshold=match_iou,
            track_activation_threshold=activation_confidence,
            high_conf_det_threshold=activation_confidence,
        )
        self._tracks: dict[int, PersonTrack] = {}
        self._next_id = 1

    def reset(self) -> None:
        self._tracker.reset()
        self._tracks.clear()
        # The library resets its allocator. Public IDs deliberately do not restart.

    def update(
        self, frame: Frame, detections: Sequence[PersonDetection]
    ) -> tuple[PersonTrack, ...]:
        boxes = np.array([d.bbox for d in detections], dtype=np.float32).reshape(-1, 4)
        scores = np.array([d.confidence for d in detections], dtype=np.float32)
        output = self._tracker.update(Detections(xyxy=boxes, confidence=scores))
        matched: set[int] = set()
        if output.tracker_id is None or output.confidence is None:
            raise RuntimeError("ByteTrack returned no track IDs or confidence")
        for raw_id, box, confidence in zip(
            output.tracker_id, output.xyxy, output.confidence, strict=True
        ):
            key = int(raw_id)
            if key < 0:
                continue  # A new candidate is confirmed on the next matched frame.
            matched.add(key)
            previous = self._tracks.get(key)
            bbox = tuple(float(v) for v in box)
            x1, y1, x2, y2 = bbox
            if previous is None:
                self._tracks[key] = PersonTrack(
                    self._next_id,
                    self._camera_id,
                    self._run_id,
                    (x1, y1, x2, y2),
                    float(confidence),
                    frame.captured_at,
                    frame.captured_at,
                    frame.source_ts_ms,
                    frame.source_ts_ms,
                    1,
                    1,
                    0,
                    PersonState.NORMAL,
                )
                self._next_id += 1
            else:
                self._tracks[key] = replace(
                    previous,
                    bbox=(x1, y1, x2, y2),
                    confidence=float(confidence),
                    last_seen=frame.captured_at,
                    last_source_ts_ms=frame.source_ts_ms,
                    age=previous.age + 1,
                    hits=previous.hits + 1,
                    missed_frames=0,
                    state=PersonState.NORMAL,
                )
        expired: set[int] = set()
        for key, track in list(self._tracks.items()):
            if key in matched:
                continue
            missed = track.missed_frames + 1
            if missed >= self._max_age:
                expired.add(key)
                del self._tracks[key]
            else:
                self._tracks[key] = replace(
                    track, age=track.age + 1, missed_frames=missed, state=PersonState.LOST
                )
        # Enforce the domain's exact >= N boundary before the next association.
        # No expired internal track may resurrect a public ID; no historical ID map grows.
        if expired:
            self._tracker.tracks = [t for t in self._tracker.tracks if t.tracker_id not in expired]
        return tuple(sorted(self._tracks.values(), key=lambda t: t.track_id))
