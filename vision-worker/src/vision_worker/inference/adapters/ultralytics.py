"""Ultralytics is isolated here. Model/device/class validation and warmup are fail-fast."""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import numpy as np
import torch
from ultralytics.engine.results import Results
from ultralytics.models.yolo.model import YOLO

from vision_worker.cameras.frame import Frame
from vision_worker.inference.detector import PersonDetection
from vision_worker.inference.manifest import ModelManifest, read_manifest, verify_weights


class UltralyticsPersonDetector:
    def __init__(self, path: Path, device: str, iou: float, threads: int = 2) -> None:
        self.manifest: ModelManifest = read_manifest(path)
        weights = verify_weights(path, self.manifest)
        self.device = "cuda" if device == "auto" and torch.cuda.is_available() else device
        if self.device == "auto":
            self.device = "cpu"
        if self.device == "cuda" and not torch.cuda.is_available():
            raise ValueError("CUDA requested but not available")
        torch.set_num_threads(threads)
        self._iou = iou
        self._model = YOLO(str(weights))
        if self._model.names.get(self.manifest.person_class_id) != "person":
            raise ValueError("manifest person_class_id is not the model's person class")
        size = self.manifest.input_size
        self.detect(
            [Frame(np.zeros((size, size, 3), dtype=np.uint8), 0, 0, datetime.now(UTC))], 0.25
        )
        # Ultralytics CPU predictor setup resets PyTorch threads during first predict.
        # Restore the explicit worker setting after that one-time setup/warmup.
        torch.set_num_threads(threads)
        self.threads = torch.get_num_threads()

    def detect(self, frames: Sequence[Frame], confidence: float) -> list[list[PersonDetection]]:
        if not frames:
            return []
        predictions = cast(
            list[Results],
            self._model.predict(
                source=[frame.image for frame in frames],
                imgsz=self.manifest.input_size,
                classes=[self.manifest.person_class_id],
                conf=confidence,
                iou=self._iou,
                device=self.device,
                verbose=False,
            ),
        )
        results: list[list[PersonDetection]] = []
        for frame, prediction in zip(frames, predictions, strict=True):
            width, height = frame.size
            detections = []
            if prediction.boxes is not None:
                for box, score in zip(
                    cast(torch.Tensor, prediction.boxes.xyxy).cpu().tolist(),
                    cast(torch.Tensor, prediction.boxes.conf).cpu().tolist(),
                    strict=True,
                ):
                    x1, y1, x2, y2 = box
                    clipped = (
                        max(0.0, min(width, x1)),
                        max(0.0, min(height, y1)),
                        max(0.0, min(width, x2)),
                        max(0.0, min(height, y2)),
                    )
                    if clipped[2] > clipped[0] and clipped[3] > clipped[1]:
                        detections.append(PersonDetection(clipped, float(score)))
            results.append(detections)
        return results
