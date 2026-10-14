"""Runtime-independent person detector contract. Coordinates refer to the original image."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from vision_worker.cameras.frame import Frame


@dataclass(frozen=True, slots=True)
class PersonDetection:
    bbox: tuple[float, float, float, float]
    confidence: float


class PersonDetector(Protocol):
    def detect(self, frames: Sequence[Frame], confidence: float) -> list[list[PersonDetection]]: ...
