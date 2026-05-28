from typing import Dict, Any, List, Optional
import cv2
import numpy as np

#Цвета
COLOR_PERSON_NORMAL     = (0, 255, 0)      # зелёный
COLOR_PERSON_CARRY      = (0, 220, 100)    # тёмно-зелёный
COLOR_PERSON_EXIT       = (200, 0, 255)    # фиолетовый
COLOR_PERSON_CARRY_EXIT = (255, 200, 0)    # голубой

COLOR_BOX               = (0, 165, 255)    # оранжевый
COLOR_PALLET            = (0, 255, 255)    # жёлтый
COLOR_FORKLIFT          = (0, 0, 255)      # красный
COLOR_OBJECT_DEFAULT    = (180, 180, 0)    # тёмно-голубой

COLOR_EXIT_ZONE         = (255, 0, 255)    # магента
COLOR_EXIT_LINE         = (255, 0, 255)

COLOR_SKELETON          = (255, 255, 0)    # голубой
COLOR_KEYPOINT          = (0, 255, 255)    # жёлтый

#Skeleton connections (COCO 17)
SKELETON_CONNECTIONS = [
    (0, 1), (0, 2), (1, 3), (2, 4),       # head
    (5, 6),                                  # shoulders
    (5, 7), (7, 9),                          # left arm
    (6, 8), (8, 10),                         # right arm
    (5, 11), (6, 12),                        # torso
    (11, 12),                                # hips
    (11, 13), (13, 15),                      # left leg
    (12, 14), (14, 16),                      # right leg
]

# Цвета для разных частей скелета
SKELETON_COLORS = {
    # head
    (0, 1): (255, 200, 200), (0, 2): (255, 200, 200),
    (1, 3): (255, 200, 200), (2, 4): (255, 200, 200),
    # shoulders
    (5, 6): (255, 255, 0),
    # left arm (синий)
    (5, 7): (255, 150, 0), (7, 9): (255, 100, 0),
    # right arm (зелёный)
    (6, 8): (0, 255, 150), (8, 10): (0, 255, 100),
    # torso
    (5, 11): (200, 200, 200), (6, 12): (200, 200, 200),
    # hips
    (11, 12): (200, 200, 0),
    # left leg (синий)
    (11, 13): (255, 100, 50), (13, 15): (255, 50, 50),
    # right leg (зелёный)
    (12, 14): (50, 255, 100), (14, 16): (50, 255, 50),
}


def _person_color(d: Dict[str, Any]) -> tuple:
    if d.get("carrying") and d.get("in_exit_zone"):
        return COLOR_PERSON_CARRY_EXIT
    if d.get("in_exit_zone"):
        return COLOR_PERSON_EXIT
    if d.get("carrying"):
        return COLOR_PERSON_CARRY
    return COLOR_PERSON_NORMAL


def _object_color(d: Dict[str, Any]) -> tuple:
    cls_name = str(d.get("cls_name", "")).lower()
    if "forklift" in cls_name:
        return COLOR_FORKLIFT
    if "pallet" in cls_name:
        return COLOR_PALLET
    if "box" in cls_name:
        return COLOR_BOX
    return COLOR_OBJECT_DEFAULT


def draw_poly(frame, poly_norm, color, thickness=2):
    h, w = frame.shape[:2]
    pts = [[int(x * w), int(y * h)] for x, y in poly_norm]
    if len(pts) >= 3:
        pts_np = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(frame, [pts_np], isClosed=True, color=color, thickness=thickness)


def draw_line(frame, line_norm, color, thickness=2):
    h, w = frame.shape[:2]
    if not line_norm or len(line_norm) != 2:
        return
    (x1, y1), (x2, y2) = line_norm
    cv2.line(frame, (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h)), color, thickness)


def draw_skeleton(frame, keypoints_norm, min_conf=0.3):
    #Рисует скелет по нормированным keypoints.
    #keypoints_norm: list of [x_norm, y_norm, confidence] — 17 точек COCO
    if keypoints_norm is None or len(keypoints_norm) < 17:
        return

    h, w = frame.shape[:2]

    # денормализуем точки
    pts = []
    for kp in keypoints_norm:
        kx, ky, kc = kp
        pts.append((int(kx * w), int(ky * h), float(kc)))

    # рисуем соединения
    for (i, j) in SKELETON_CONNECTIONS:
        if i >= len(pts) or j >= len(pts):
            continue
        x1, y1, c1 = pts[i]
        x2, y2, c2 = pts[j]
        if c1 < min_conf or c2 < min_conf:
            continue
        color = SKELETON_COLORS.get((i, j), COLOR_SKELETON)
        cv2.line(frame, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)

    # рисуем точки
    for idx, (x, y, c) in enumerate(pts):
        if c < min_conf:
            continue
        # голова — маленькие точки, тело — побольше
        radius = 3 if idx <= 4 else 4
        cv2.circle(frame, (x, y), radius, COLOR_KEYPOINT, -1, cv2.LINE_AA)


def draw_overlay_bgr(frame_bgr: np.ndarray, overlay: Dict[str, Any]):
    if frame_bgr is None:
        return None

    h, w = frame_bgr.shape[:2]

    cfg = (overlay or {}).get("config") or {}
    exit_zone = cfg.get("exit_zone")
    exit_line = cfg.get("exit_line")

    if exit_zone:
        draw_poly(frame_bgr, exit_zone, COLOR_EXIT_ZONE, 2)
    if exit_line:
        draw_line(frame_bgr, exit_line, COLOR_EXIT_LINE, 2)

    dets = (overlay or {}).get("detections") or []
    for d in dets:
        ent = d.get("entity", "person")
        bbox = d.get("bbox")
        if not bbox:
            continue

        x1 = max(0, min(w - 1, int(bbox[0] * w)))
        y1 = max(0, min(h - 1, int(bbox[1] * h)))
        x2 = max(0, min(w - 1, int(bbox[2] * w)))
        y2 = max(0, min(h - 1, int(bbox[3] * h)))

        if ent == "object":
            color = _object_color(d)
            cls = d.get("cls_name", "obj")
            label = f"{cls} {d.get('conf', 0):.2f} T{d.get('track_id', -1)}"
        else:
            color = _person_color(d)
            parts = [f"ID:{d.get('track_id', -1)}"]
            if d.get("carrying"):
                carry_obj = d.get("carry_obj")
                if carry_obj:
                    parts.append(f"carrying:{carry_obj.get('cls_name', '?')}")
                else:
                    parts.append("carrying")
            if d.get("in_exit_zone"):
                parts.append("EXIT")
            label = " ".join(parts)

        # bbox
        cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), color, 2)

        # label background
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        label_y = max(th + 4, y1 - 4)
        cv2.rectangle(frame_bgr, (x1, label_y - th - 4), (x1 + tw + 4, label_y), color, -1)
        cv2.putText(frame_bgr, label, (x1 + 2, label_y - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

        # skeleton
        if ent == "person":
            kpts = d.get("keypoints")
            if kpts and len(kpts) >= 17:
                draw_skeleton(frame_bgr, kpts, min_conf=0.3)

    return frame_bgr


def draw_zones_only_bgr(frame_bgr, exit_line, exit_zone):
    if frame_bgr is None:
        return None
    if exit_zone:
        draw_poly(frame_bgr, exit_zone, COLOR_EXIT_ZONE, 2)
    if exit_line:
        draw_line(frame_bgr, exit_line, COLOR_EXIT_LINE, 2)
    return frame_bgr