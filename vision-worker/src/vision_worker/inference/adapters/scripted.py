"""Detections use the same source time and scenario as the synthetic frame renderer."""

from collections.abc import Sequence

from vision_worker.cameras.frame import Frame
from vision_worker.cameras.scenario import Scenario
from vision_worker.inference.detector import PersonDetection


class ScriptedPersonDetector:
    def __init__(self, scenario: Scenario) -> None:
        self._scenario = scenario

    def detect(self, frames: Sequence[Frame], confidence: float) -> list[list[PersonDetection]]:
        results = []
        for frame in frames:
            width, height = frame.size
            results.append(
                [
                    PersonDetection((x1 * width, y1 * height, x2 * width, y2 * height), 1.0)
                    for _, (x1, y1, x2, y2) in self._scenario.boxes_at(frame.source_ts_ms / 1000)
                    if confidence <= 1.0
                ]
            )
        return results
