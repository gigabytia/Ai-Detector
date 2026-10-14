"""One immutable detection result tied to the exact captured frame."""

from dataclasses import dataclass
from uuid import UUID

from vision_worker.cameras.frame import Frame
from vision_worker.inference.detector import PersonDetection


@dataclass(frozen=True, slots=True)
class DetectionResult:
    camera_id: UUID
    run_id: UUID
    frame: Frame
    detections: tuple[PersonDetection, ...]
    inference_ms: float
