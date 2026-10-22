"""1 Hz observed samples and final track sessions, no database/network in offer."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from ai_detector_core.telemetry.analytics import CameraSample, Segment, TrackSession
from vision_worker.messaging.analytics import AnalyticsPublisher
from vision_worker.pipeline.results import DetectionResult

logger = logging.getLogger(__name__)


@dataclass
class ObservedTrack:
    started: datetime
    at: datetime
    state: str
    since: datetime
    segments: list[Segment] = field(default_factory=list)
    truncated: bool = False


class AnalyticsCollector:
    def __init__(self, publisher: AnalyticsPublisher) -> None:
        self.publisher = publisher
        self.tracks: dict[tuple[UUID, UUID, int], ObservedTrack] = {}
        self.samples: dict[tuple[UUID, UUID], CameraSample] = {}
        self.last: dict[tuple[UUID, UUID], datetime] = {}

    def _finish(self, key: tuple[UUID, UUID, int]) -> None:
        t = self.tracks.pop(key)
        self._segment(t, t.at)
        self.publisher.offer(
            TrackSession(
                id=uuid5(NAMESPACE_URL, f"track:{key}"),
                camera_id=key[0],
                run_id=key[1],
                track_id=key[2],
                started_at=t.started,
                ended_at=t.at,
                segments=tuple(t.segments),
                truncated=t.truncated,
            )
        )

    @staticmethod
    def _segment(t: ObservedTrack, at: datetime) -> None:
        if len(t.segments) < 2048:
            t.segments.append(Segment(state=t.state, start=t.since, end=at))
        elif not t.truncated:
            t.truncated = True
            logger.warning("track timeline truncated at 2048 segments")

    def retain(self, active: set[tuple[UUID, UUID]]) -> None:
        for key in list(self.tracks):
            if key[:2] not in active:
                self._finish(key)
        for sample_key in list(self.samples):
            if sample_key not in active:
                self.publisher.offer(self.samples.pop(sample_key))
                self.last.pop(sample_key, None)

    def offer(self, result: DetectionResult) -> None:
        key = result.camera_id, result.run_id
        at = result.frame.captured_at
        previous = self.last.get(key)
        if previous is not None and at < previous:
            logger.warning("out-of-order analytics frame ignored")
            return
        gap = (at - previous).total_seconds() if previous else 0.0
        self.last[key] = at
        old = self.samples.get(key)
        bucket = int(at.timestamp())
        if old is not None and int(old.at.timestamp()) != bucket:
            self.publisher.offer(old)
            old = None
        duration = (old.observed_seconds if old else 0.0) + (gap if 0 <= gap <= 2 else 0.0)
        self.samples[key] = CameraSample(
            id=uuid5(NAMESPACE_URL, f"sample:{key}:{bucket}"),
            camera_id=key[0],
            run_id=key[1],
            at=at,
            persons=len(result.detections),
            persons_in_zone=sum(t.state.value == "IN_DANGER_ZONE" for t in result.tracks),
            observed_seconds=duration,
        )
        active = {t.track_id for t in result.tracks}
        for tid in [k for k in self.tracks if k[:2] == key and k[2] not in active]:
            self._finish(tid)
        for track in result.tracks:
            tk = (*key, track.track_id)
            t = self.tracks.get(tk)
            if t is None:
                if len(self.tracks) >= 4096:
                    logger.error("analytics active track capacity exceeded")
                    continue
                self.tracks[tk] = ObservedTrack(at, at, track.state.value, at)
            else:
                if gap > 2:
                    self._segment(t, t.at)
                    t.since, t.state = t.at, "LOST"
                    self._segment(t, at)
                    t.since, t.state = at, track.state.value
                if t.state != track.state.value:
                    self._segment(t, at)
                    t.since, t.state = at, track.state.value
                t.at = at
