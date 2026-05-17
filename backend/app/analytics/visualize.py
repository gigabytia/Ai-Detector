import cv2
import numpy as np
from ..config import SETTINGS, SKELETON_EDGES

POSE_COLORS_BGR = {
    "standing": (0, 255, 0),
    "walking": (255, 0, 0),
    "sitting": (0, 165, 255),
    "lying": (255, 0, 255),
    "hand_raised": (0, 0, 255),
    "unknown": (128, 128, 128),
}

def _kp_ok(kp, bbox, thr=0.10) -> bool:
    # kp = [x_norm, y_norm, conf]
    if kp is None or len(kp) < 3:
        return False

    x = float(kp[0]); y = float(kp[1]); c = float(kp[2])

    if not np.isfinite(x) or not np.isfinite(y) or not np.isfinite(c):
        return False

    if c < thr:
        return False

    # мусорная точка (0,0)
    if x <= 1e-4 and y <= 1e-4:
        return False

    if x < 0.0 or x > 1.0 or y < 0.0 or y > 1.0:
        return False

    if bbox is None or len(bbox) != 4:
        return True

    x1, y1, x2, y2 = map(float, bbox)
    bw = max(1e-6, x2 - x1)
    bh = max(1e-6, y2 - y1)
    mx = bw * 0.60
    my = bh * 0.60

    return (x >= x1 - mx and x <= x2 + mx and y >= y1 - my and y <= y2 + my)

def draw_overlay_bgr(frame_bgr: np.ndarray, overlay: dict):
    if frame_bgr is None:
        return None

    h, w = frame_bgr.shape[:2]
    dets = (overlay or {}).get("detections", []) or []

    thr = float(SETTINGS.KP_DRAW_THR)

    for det in dets:
        pose = det.get("pose", "unknown")
        tid = det.get("track_id", -1)
        color = POSE_COLORS_BGR.get(pose, (128, 128, 128))

        bbox = det.get("bbox", None)
        if bbox and len(bbox) == 4:
            x1 = int(float(bbox[0]) * w)
            y1 = int(float(bbox[1]) * h)
            x2 = int(float(bbox[2]) * w)
            y2 = int(float(bbox[3]) * h)

            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(0, min(w - 1, x2))
            y2 = max(0, min(h - 1, y2))

            cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame_bgr, f"ID:{tid} {pose}", (x1, max(15, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)

        kps = det.get("keypoints", None)
        if not kps or len(kps) < 17:
            continue

        # skeleton lines
        for i, j in SKELETON_EDGES:
            ki = kps[i] if i < len(kps) else None
            kj = kps[j] if j < len(kps) else None
            bbox = det.get("bbox", None)
            if not _kp_ok(ki, bbox, thr) or not _kp_ok(kj, bbox, thr):
                continue
            x1p = int(float(ki[0]) * w)
            y1p = int(float(ki[1]) * h)
            x2p = int(float(kj[0]) * w)
            y2p = int(float(kj[1]) * h)
            cv2.line(frame_bgr, (x1p, y1p), (x2p, y2p), (255, 255, 0), 2)

        # points
        for kp in kps:
            bbox = det.get("bbox", None)
            if not _kp_ok(kp, bbox, thr):
                continue
            x = int(float(kp[0]) * w)
            y = int(float(kp[1]) * h)
            cv2.circle(frame_bgr, (x, y), 3, (0, 255, 255), -1)

    return frame_bgr