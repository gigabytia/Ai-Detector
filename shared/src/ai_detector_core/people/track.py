"""Immutable person runtime state; identity is scoped to camera and run."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class PersonState(StrEnum):
    NORMAL = "NORMAL"
    LOST = "LOST"


@dataclass(frozen=True, slots=True)
class PersonTrack:
    track_id: int
    camera_id: UUID
    run_id: UUID
    bbox: tuple[float, float, float, float]
    confidence: float
    first_seen: datetime
    last_seen: datetime
    first_source_ts_ms: float
    last_source_ts_ms: float
    age: int  # processed frames since confirmation, including missed frames
    hits: int
    missed_frames: int
    state: PersonState

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return (x1 + x2) / 2, (y1 + y2) / 2

    @property
    def anchor(self) -> tuple[float, float]:
        x1, _, x2, y2 = self.bbox
        return (x1 + x2) / 2, y2
