"""Own zone engines on the same executor as trackers; scene generation is durable."""

from dataclasses import dataclass, replace
from typing import Literal

from ai_detector_core.cameras.config import CameraConfig
from ai_detector_core.ports.clock import Clock, SystemClock
from vision_worker.pipeline.results import DetectionResult
from vision_worker.rules.zone_engine import ZoneEngine
from vision_worker.tracking.registry import TrackKey


@dataclass
class Entry:
    engine: ZoneEngine
    epoch: int
    size: tuple[int, int]


class SceneRegistry:
    def __init__(
        self,
        clock: Clock | None = None,
        min_hits: int = 3,
        severity: Literal["critical", "warning", "info"] = "critical",
    ) -> None:
        self._clock = clock if clock is not None else SystemClock()
        self._min_hits = min_hits
        self._severity = severity
        self._entries: dict[TrackKey, Entry] = {}

    def retain(self, active: set[TrackKey]) -> None:
        for key in self._entries.keys() - active:
            del self._entries[key]

    def update(self, result: DetectionResult, config: CameraConfig) -> DetectionResult:
        key = result.camera_id, result.run_id
        frame = result.frame
        entry = self._entries.get(key)
        if (
            entry is None
            or frame.discontinuity
            or entry.epoch != frame.source_epoch
            or entry.size != frame.size
        ):
            entry = Entry(
                ZoneEngine(self._clock, self._min_hits, self._severity),
                frame.source_epoch,
                frame.size,
            )
            self._entries[key] = entry
        tracks, events = entry.engine.update(frame, result.tracks, result.zones, config)
        return replace(result, tracks=tracks, events=events)
