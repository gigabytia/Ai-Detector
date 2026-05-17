from dataclasses import dataclass, field
from collections import deque
from typing import Dict, List, Tuple
import numpy as np
from ..config import SETTINGS

def iou_xyxy(a: np.ndarray, b: np.ndarray) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    iw = max(0.0, inter_x2 - inter_x1)
    ih = max(0.0, inter_y2 - inter_y1)
    inter = iw * ih
    area_a = max(0.0, (ax2 - ax1)) * max(0.0, (ay2 - ay1))
    area_b = max(0.0, (bx2 - bx1)) * max(0.0, (by2 - by1))
    union = area_a + area_b - inter
    return float(inter / union) if union > 0 else 0.0

@dataclass
class PoseHyst:
    state: str = "unknown"
    cand: str = "unknown"
    cand_n: int = 0

    def apply(self, proposed: str) -> str:
        if self.state == proposed:
            self.cand = proposed
            self.cand_n = 0
            return self.state

        if self.cand != proposed:
            self.cand = proposed
            self.cand_n = 1
        else:
            self.cand_n += 1

        if self.cand_n >= max(1, SETTINGS.POSE_ENTER_FRAMES):
            self.state = proposed
            self.cand = proposed
            self.cand_n = 0

        return self.state

@dataclass
class HandHyst:
    state: bool = False
    up_n: int = 0
    down_n: int = 0

    def apply(self, proposed: bool) -> bool:
        if proposed:
            self.down_n = 0
            if self.state:
                return True
            self.up_n += 1
            if self.up_n >= max(1, SETTINGS.HAND_RAISE_ENTER_FRAMES):
                self.state = True
                self.up_n = 0
                return True
            return False
        else:
            self.up_n = 0
            if not self.state:
                return False
            self.down_n += 1
            if self.down_n >= max(1, SETTINGS.HAND_RAISE_EXIT_FRAMES):
                self.state = False
                self.down_n = 0
                return False
            return True

@dataclass
class Track:
    id: int
    bbox_xyxy: np.ndarray
    miss: int = 0
    motion: deque = field(default_factory=lambda: deque(maxlen=10))  # (t, cx, cy, bh)
    pose_h: PoseHyst = field(default_factory=PoseHyst)
    hand_h: HandHyst = field(default_factory=HandHyst)

class SimpleTracker:
    def __init__(self, iou_thr: float = 0.35, max_miss: int = 20):
        self.iou_thr = float(iou_thr)
        self.max_miss = int(max_miss)
        self._next_id = 1
        self.tracks: Dict[int, Track] = {}

    def _new_track(self, bbox: np.ndarray) -> Track:
        tid = self._next_id
        self._next_id += 1
        tr = Track(id=tid, bbox_xyxy=bbox.copy(), miss=0)
        self.tracks[tid] = tr
        return tr

    def update(self, det_bboxes: List[np.ndarray]) -> List[Tuple[Track, int]]:
        for tr in self.tracks.values():
            tr.miss += 1

        track_ids = list(self.tracks.keys())
        unmatched = set(range(len(det_bboxes)))
        assignments: List[Tuple[Track, int]] = []

        if track_ids and det_bboxes:
            pairs = []
            for tid in track_ids:
                for di in range(len(det_bboxes)):
                    pairs.append((iou_xyxy(self.tracks[tid].bbox_xyxy, det_bboxes[di]), tid, di))
            pairs.sort(reverse=True, key=lambda x: x[0])

            used_tracks = set()
            for val, tid, di in pairs:
                if val < self.iou_thr:
                    break
                if tid in used_tracks or di not in unmatched:
                    continue
                used_tracks.add(tid)
                unmatched.remove(di)
                tr = self.tracks[tid]
                tr.bbox_xyxy = det_bboxes[di].copy()
                tr.miss = 0
                assignments.append((tr, di))

        for di in list(unmatched):
            tr = self._new_track(det_bboxes[di])
            assignments.append((tr, di))

        for tid in [tid for tid, tr in self.tracks.items() if tr.miss > self.max_miss]:
            del self.tracks[tid]

        return assignments

def update_motion(tr: Track, t_sec: float):
    x1, y1, x2, y2 = map(float, tr.bbox_xyxy)
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    bh = max(1.0, y2 - y1)
    tr.motion.append((float(t_sec), float(cx), float(cy), float(bh)))

def is_walking(tr: Track) -> bool:
    if len(tr.motion) < 6:
        return False

    t0, cx0, cy0, _ = tr.motion[0]
    t1, cx1, cy1, _ = tr.motion[-1]
    dt = max(1e-3, float(t1 - t0))

    dist = float(np.hypot(cx1 - cx0, cy1 - cy0))
    speed = dist / dt

    bh = max(1.0, float(np.median([x[3] for x in tr.motion])))

    return (speed > SETTINGS.WALK_SPEED_ABS_PX_PER_SEC) and ((speed / bh) > SETTINGS.WALK_SPEED_REL_TO_BBOXH)