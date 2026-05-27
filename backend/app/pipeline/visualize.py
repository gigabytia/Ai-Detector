# backend/app/pipeline/visualize.py
from typing import Dict, Any, List, Optional
import cv2
import numpy as np

# цвета
PERSON_NORMAL_COLOR  = (0, 255, 0)       # зелёный
PERSON_CARRY_COLOR   = (0, 200, 50)      # зелёный темнее
PERSON_EXIT_COLOR    = (200, 0, 255)     # фиолетовый
PERSON_CARRY_EXIT_COLOR = (255, 200, 0) # голубой
OBJECT_COLOR         = (0, 180, 255)     # оранжевый
EXIT_ZONE_COLOR      = (255, 0, 255)     # магента
EXIT_LINE_COLOR      = (255, 0, 255)


def _person_color(d: Dict[str, Any]):
    if d.get("carrying") and d.get("in_exit_zone"):
        return PERSON_CARRY_EXIT_COLOR
    if d.get("in_exit_zone"):
        return PERSON_EXIT_COLOR
    if d.get("carrying"):
        return PERSON_CARRY_COLOR
    return PERSON_NORMAL_COLOR


def draw_poly(
    frame: np.ndarray,
    poly_norm: List[List[float]],
    color,
    thickness: int = 2,
):
    h, w = frame.shape[:2]
    pts = [[int(x * w), int(y * h)] for x, y in poly_norm]
    if len(pts) >= 3:
        pts_np = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(frame, [pts_np], isClosed=True, color=color, thickness=thickness)


def draw_line(
    frame: np.ndarray,
    line_norm: List[List[float]],
    color,
    thickness: int = 2,
):
    h, w = frame.shape[:2]
    if not line_norm or len(line_norm) != 2:
        return
    (x1, y1), (x2, y2) = line_norm
    p1 = (int(x1 * w), int(y1 * h))
    p2 = (int(x2 * w), int(y2 * h))
    cv2.line(frame, p1, p2, color, thickness)


def draw_overlay_bgr(frame_bgr: np.ndarray, overlay: Dict[str, Any]):
    """Рисует зоны, bbox, метки на кадре in-place."""
    if frame_bgr is None:
        return None
    h, w = frame_bgr.shape[:2]

    cfg       = (overlay or {}).get("config") or {}
    exit_zone = cfg.get("exit_zone")
    exit_line = cfg.get("exit_line")

    if exit_zone:
        draw_poly(frame_bgr, exit_zone, EXIT_ZONE_COLOR, 2)
    if exit_line:
        draw_line(frame_bgr, exit_line, EXIT_LINE_COLOR, 2)

    dets = (overlay or {}).get("detections") or []
    for d in dets:
        ent  = d.get("entity", "person")
        bbox = d.get("bbox")
        if not bbox:
            continue

        x1 = max(0, min(w - 1, int(bbox[0] * w)))
        y1 = max(0, min(h - 1, int(bbox[1] * h)))
        x2 = max(0, min(w - 1, int(bbox[2] * w)))
        y2 = max(0, min(h - 1, int(bbox[3] * h)))

        if ent == "object":
            color = OBJECT_COLOR
            label = (
                f"{d.get('cls_name', 'obj')} "
                f"{d.get('conf', 0):.2f} "
                f"T{d.get('track_id', -1)}"
            )
        else:
            color = _person_color(d)
            parts = [f"ID:{d.get('track_id', -1)}"]
            if d.get("carrying"):
                parts.append("carrying")
            if d.get("in_exit_zone"):
                parts.append("exit")
            label = " ".join(parts)

        cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame_bgr, label,
            (x1, max(14, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA,
        )

    return frame_bgr


def draw_zones_only_bgr(
    frame_bgr: np.ndarray,
    exit_line: Optional[List],
    exit_zone: Optional[List],
):
    """Рисует только зоны/линии (без боксов)."""
    if frame_bgr is None:
        return None
    if exit_zone:
        draw_poly(frame_bgr, exit_zone, EXIT_ZONE_COLOR, 2)
    if exit_line:
        draw_line(frame_bgr, exit_line, EXIT_LINE_COLOR, 2)
    return frame_bgr