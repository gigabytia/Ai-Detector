"""Finite line crossing: stable signed side, hysteresis, bounded confidence window.

First stable observation is baseline. LOST freezes side, but contributes a miss
in the confidence window. Recovery on the opposite side counts (ADR-013).
"""

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from math import hypot
from typing import Literal
from uuid import UUID

from ai_detector_core.cameras.config import CameraConfig
from ai_detector_core.events.domain import DomainEvent, LineCrossMetadata
from ai_detector_core.lines.model import LineSpec
from ai_detector_core.people.track import PersonState, PersonTrack
from ai_detector_core.ports.clock import Clock
from vision_worker.cameras.frame import Frame

logger = logging.getLogger(__name__)


@dataclass
class Side:
    value: int = 0


class LineEngine:
    def __init__(
        self,
        clock: Clock,
        min_hits: int = 3,
        hysteresis: float = 0.01,
        severity: Literal["critical", "warning", "info"] = "warning",
    ) -> None:
        if min_hits < 1 or not 0 < hysteresis <= 0.1:
            raise ValueError("Invalid line confirmation settings")
        self._clock, self._min_hits = clock, min_hits
        self._hysteresis, self._severity = hysteresis, severity
        self._lines: dict[UUID, LineSpec] = {}
        self._sides: dict[tuple[int, UUID], Side] = {}
        self._cooldown: dict[int, datetime] = {}
        self._windows: dict[int, deque[float | None]] = {}

    def update(
        self,
        frame: Frame,
        tracks: tuple[PersonTrack, ...],
        lines: tuple[LineSpec, ...],
        config: CameraConfig,
    ) -> tuple[DomainEvent, ...]:
        enabled = {line.id: line for line in lines if line.enabled}
        changed = {
            lid
            for lid, old in self._lines.items()
            if lid not in enabled or (old.p1, old.p2) != (enabled[lid].p1, enabled[lid].p2)
        }
        active = {t.track_id for t in tracks}
        self._sides = {
            k: v for k, v in self._sides.items() if k[0] in active and k[1] not in changed
        }
        self._windows = {k: v for k, v in self._windows.items() if k in active}
        self._cooldown = {k: v for k, v in self._cooldown.items() if k in active}
        self._lines = enabled
        events = []
        width, height = frame.size
        for track in tracks:
            window = self._windows.setdefault(track.track_id, deque(maxlen=self._min_hits))
            window.append(None if track.state == PersonState.LOST else track.confidence)
            if track.state == PersonState.LOST:
                continue
            ax, ay = track.anchor[0] / width, track.anchor[1] / height
            for line in enabled.values():
                dx, dy = line.p2.x - line.p1.x, line.p2.y - line.p1.y
                distance = (dx * (ay - line.p1.y) - dy * (ax - line.p1.x)) / hypot(dx, dy)
                if abs(distance) <= self._hysteresis + 1e-12:
                    continue
                side = 1 if distance > 0 else -1
                state = self._sides.setdefault((track.track_id, line.id), Side())
                previous, state.value = state.value, side
                if previous == 0 or previous == side or track.hits < self._min_hits:
                    continue
                projection = ((ax - line.p1.x) * dx + (ay - line.p1.y) * dy) / (dx * dx + dy * dy)
                if not -1e-9 <= projection <= 1 + 1e-9:
                    continue
                now = self._clock.now()
                last = self._cooldown.get(track.track_id)
                if (
                    last is not None
                    and (now - last).total_seconds() < config.event_cooldown_seconds
                ):
                    logger.debug(
                        "line crossing suppressed by cooldown",
                        extra={
                            "camera_id": str(track.camera_id),
                            "run_id": str(track.run_id),
                            "track_id": track.track_id,
                            "line_id": str(line.id),
                        },
                    )
                    continue
                self._cooldown[track.track_id] = now
                matched = [score for score in window if score is not None]
                mean, stability = sum(matched) / len(matched), len(matched) / len(window)
                x1, y1, x2, y2 = track.bbox
                events.append(
                    DomainEvent(
                        camera_id=track.camera_id,
                        run_id=track.run_id,
                        track_id=track.track_id,
                        zone_id=None,
                        line_id=line.id,
                        type="PERSON_CROSSED_LINE",
                        severity=self._severity,
                        occurred_at=frame.captured_at,
                        source_ts_ms=frame.source_ts_ms,
                        detector_confidence=mean,
                        event_confidence=mean * stability,
                        message=f"Человек #{track.track_id} пересёк линию «{line.name}»",
                        metadata=LineCrossMetadata(
                            bbox=(x1 / width, y1 / height, x2 / width, y2 / height),
                            anchor=(ax, ay),
                            stability=stability,
                            direction="LEFT_TO_RIGHT" if previous < side else "RIGHT_TO_LEFT",
                            line_name=line.name,
                            p1=(line.p1.x, line.p1.y),
                            p2=(line.p2.x, line.p2.y),
                        ),
                    )
                )
        return tuple(events)
