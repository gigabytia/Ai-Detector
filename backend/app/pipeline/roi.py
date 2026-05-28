from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from ..config import SETTINGS
from .detector import YOLODetector

@dataclass
class ROICrop:
    camera_id: int
    person_track_id: int
    x1: int
    y1: int
    x2: int
    y2: int
    crop_bgr: np.ndarray

class ROIPipeline:
    def __init__(self, det: YOLODetector, roi_det: Optional[YOLODetector] = None):
        self.det = det
        self.roi_det = roi_det if roi_det is not None else det

    def build_crops(self, frame_bgr: np.ndarray, people: List[Dict[str, Any]]) -> List[ROICrop]:
        h, w = frame_bgr.shape[:2]
        crops: List[ROICrop] = []

        # сортируем сначала самые маленькие
        people_sorted = sorted(people, key=lambda p: (p["bbox_px"][3] - p["bbox_px"][1]))

        for p in people_sorted[:SETTINGS.ROI_MAX_CROPS_PER_TICK]:
            x1, y1, x2, y2 = p["bbox_px"]
            bh = max(1, y2 - y1)

            # чуть расширим
            pad = int(0.20 * bh)
            cx1 = max(0, x1 - pad)
            cy1 = max(0, y1 - pad)
            cx2 = min(w - 1, x2 + pad)
            cy2 = min(h - 1, y2 + pad)

            crop = frame_bgr[cy1:cy2, cx1:cx2]
            if crop.size == 0:
                continue

            crops.append(ROICrop(
                camera_id=int(p["camera_id"]),
                person_track_id=int(p["track_id"]),
                x1=int(cx1), y1=int(cy1), x2=int(cx2), y2=int(cy2),
                crop_bgr=crop
            ))
        return crops

    def run(self, crops: List[ROICrop]) -> List[Dict[str, Any]]:
        if not crops:
            return []

        frames = [c.crop_bgr for c in crops]
        results = self.roi_det.predict(frames, classes=None, max_det=50)

        out: List[Dict[str, Any]] = []
        for crop, r in zip(crops, results):
            if r.boxes is None or len(r.boxes) == 0:
                continue

            boxes = r.boxes.xyxy.cpu().numpy().astype(np.float32)
            confs = r.boxes.conf.cpu().numpy().astype(np.float32)
            clss = r.boxes.cls.cpu().numpy().astype(np.int32)

            names = getattr(r, "names", None) or getattr(self.roi_det.model, "names", {})  # safety

            for (x1, y1, x2, y2), cf, ci in zip(boxes, confs, clss):
                # маппинг в координаты исходного кадра
                fx1 = float(x1 + crop.x1)
                fy1 = float(y1 + crop.y1)
                fx2 = float(x2 + crop.x1)
                fy2 = float(y2 + crop.y1)

                label = str(names.get(int(ci), str(int(ci))))

                out.append({
                    "camera_id": crop.camera_id,
                    "src": "roi",
                    "person_track_id": crop.person_track_id,
                    "cls_id": int(ci),
                    "cls_name": label,
                    "conf": float(cf),
                    "bbox_xyxy_px": [fx1, fy1, fx2, fy2],
                })
        return out