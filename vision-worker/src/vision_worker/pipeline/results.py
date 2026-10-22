"""One immutable detection result tied to the exact captured frame."""

from dataclasses import dataclass
from uuid import UUID

from ai_detector_core.events.domain import DomainEvent
from ai_detector_core.lines.model import LineSpec
from ai_detector_core.people.track import PersonTrack
from ai_detector_core.zones.model import ZoneSpec
from vision_worker.cameras.frame import Frame
from vision_worker.inference.detector import PersonDetection


@dataclass(frozen=True, slots=True)
class DetectionResult:
    camera_id: UUID
    run_id: UUID
    frame: Frame
    detections: tuple[PersonDetection, ...]
    inference_ms: float
    tracks: tuple[PersonTrack, ...] = ()
    zones: tuple[ZoneSpec, ...] = ()
    events: tuple[DomainEvent, ...] = ()
    lines: tuple[LineSpec, ...] = ()
