from typing import List, Optional, Any
import numpy as np
import torch
from ultralytics import YOLO

def select_device(requested: str = "auto") -> str:
    if requested == "auto":
        if torch.cuda.is_available():
            return "cuda:0"
        return "cpu"
    if requested.startswith("cuda") and torch.cuda.is_available():
        return requested
    if requested == "cpu":
        return "cpu"
    return "cpu"

class YOLODetector:
    def __init__(self, model_path: str, device: str, imgsz: int, conf: float, iou: float):
        self.model_path = model_path
        self.device = select_device(device)
        self.ultra_device = 0 if self.device.startswith("cuda") else "cpu"

        self.imgsz = int(imgsz)
        self.conf = float(conf)
        self.iou = float(iou)

        self.model = YOLO(model_path)

        self.use_half = False
        if self.device.startswith("cuda"):
            cap = torch.cuda.get_device_capability(0)
            self.use_half = (cap[0] >= 7)

            # прогрев
            dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
            _ = self.model.predict(dummy, verbose=False, device=self.ultra_device, imgsz=self.imgsz, half=self.use_half)

    def predict(self, frames_bgr: List[np.ndarray], classes: Optional[List[int]] = None, max_det: int = 80) -> List[Any]:
        return self.model.predict(
            frames_bgr,
            verbose=False,
            device=self.ultra_device,
            imgsz=self.imgsz,
            conf=self.conf,
            iou=self.iou,
            half=self.use_half,
            classes=classes,
            max_det=max_det,
        )