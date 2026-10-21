"""Tracker ownership and scene resets. Access only from the inference executor."""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from ai_detector_core.people.track import PersonTrack
from vision_worker.pipeline.results import DetectionResult
from vision_worker.tracking.bytetrack import ByteTrackPersonTracker
from vision_worker.tracking.tracker import PersonTracker

TrackKey = tuple[UUID, UUID]


@dataclass
class Entry:
    tracker: PersonTracker
    epoch: int
    size: tuple[int, int]


class TrackerRegistry:
    def __init__(
        self, factory: Callable[[UUID, UUID], PersonTracker] = ByteTrackPersonTracker
    ) -> None:
        self._factory = factory
        self._entries: dict[TrackKey, Entry] = {}

    def retain(self, active: set[TrackKey]) -> None:
        for key in self._entries.keys() - active:
            del self._entries[key]

    def update(self, result: DetectionResult) -> tuple[PersonTrack, ...]:
        key = result.camera_id, result.run_id
        frame = result.frame
        entry = self._entries.get(key)
        if entry is None:
            entry = Entry(self._factory(*key), frame.source_epoch, frame.size)
            self._entries[key] = entry
        elif frame.discontinuity or entry.epoch != frame.source_epoch or entry.size != frame.size:
            entry.tracker.reset()
        entry.epoch, entry.size = frame.source_epoch, frame.size
        try:
            return entry.tracker.update(frame, result.detections)
        except Exception:
            # A failed adapter may have mutated library state. Do not reuse that scene.
            entry.tracker.reset()
            raise
