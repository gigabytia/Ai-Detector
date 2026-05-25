from typing import Dict, Any, List, Optional
import cv2
import numpy as np

PERSON_COLOR = (0, 255, 0)
OBJECT_COLOR = (255, 180, 0)
EXIT_COLOR = (255, 0, 255)

def draw_poly(frame: np.ndarray, poly_norm: List[List[float]], color, thickness=2):
    h, w = frame.shape[:2]
    pts = []
    for x, y in poly_norm:
        pts.append([int(x * w), int(y * h)])
    if len(pts) >= 3:
        pts_np = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(frame, [pts_np], isClosed=True, color=color, thickness=thickness)

def draw_line(frame: np.ndarray, line_norm: List[List[float]], color, thickness=2):
    h, w = frame.shape[:2]
    if not line_norm or len(line_norm) != 2:
        return
    (x1, y1), (x2, y2) = line_norm
    p1 = (int(x1*w), int(y1*h))
    p2 = (int(x2*w), int(y2*h))
    cv2.line(frame, p1, p2, color, thickness)

def draw_overlay_bgr(frame_bgr: np.ndarray, overlay: Dict[str, Any]):
    if frame_bgr is None:
        return None
    h, w = frame_bgr.shape[:2]

    cfg = (overlay or {}).get("config") or {}
    exit_line = cfg.get("exit_line")
    exit_zone = cfg.get("exit_zone")

    if exit_zone:
        draw_poly(frame_bgr, exit_zone, EXIT_COLOR, 2)
    if exit_line:
        draw_line(frame_bgr, exit_line, EXIT_COLOR, 2)

    dets = (overlay or {}).get("detections", []) or []
    for d in dets:
        ent = d.get("entity", "person")
        bbox = d.get("bbox")  # norm xyxy
        if not bbox:
            continue
        x1 = int(bbox[0] * w); y1 = int(bbox[1] * h)
        x2 = int(bbox[2] * w); y2 = int(bbox[3] * h)
        x1 = max(0, min(w-1, x1)); y1 = max(0, min(h-1, y1))
        x2 = max(0, min(w-1, x2)); y2 = max(0, min(h-1, y2))

        if ent == "object":
            color = OBJECT_COLOR
            label = f"{d.get('cls_name','obj')} {d.get('conf',0):.2f} T{d.get('track_id',-1)}"
        else:
            carrying = " carrying" if d.get("carrying") else ""
            in_exit = " exit" if d.get("in_exit_zone") else ""
            label = f"ID:{d.get('track_id',-1)}{carrying}{in_exit}"

        cv2.rectangle(frame_bgr, (x1,y1), (x2,y2), color, 2)
        cv2.putText(frame_bgr, label, (x1, max(14, y1-6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

def draw_zones_only_bgr(frame_bgr: np.ndarray, exit_line, exit_zone):
    """
    Рисует только зоны/линии (без боксов/ID/скелетов).
    exit_line: [[x,y],[x,y]] в нормированных координатах
    exit_zone: [[x,y],...] в нормированных координатах
    """
    if frame_bgr is None:
        return None

    if exit_zone:
        draw_poly(frame_bgr, exit_zone, EXIT_COLOR, 2)

    if exit_line:
        draw_line(frame_bgr, exit_line, EXIT_COLOR, 2)

    return frame_bgr