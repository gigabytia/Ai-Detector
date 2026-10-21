"""Person tracking port. Call once for every processed frame, even when empty."""

from collections.abc import Sequence
from typing import Protocol

from ai_detector_core.people.track import PersonTrack
from vision_worker.cameras.frame import Frame
from vision_worker.inference.detector import PersonDetection


class PersonTracker(Protocol):
    def update(
        self, frame: Frame, detections: Sequence[PersonDetection]
    ) -> tuple[PersonTrack, ...]: ...

    def reset(self) -> None:
        """Discard scene state without reusing public IDs in the same run."""
        ...
