from typing import List, Tuple
import numpy as np
from scipy.optimize import linear_sum_assignment

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

def iou_distance(tracks_xyxy: List[np.ndarray], dets_xyxy: List[np.ndarray]) -> np.ndarray:
    if len(tracks_xyxy) == 0 or len(dets_xyxy) == 0:
        return np.zeros((len(tracks_xyxy), len(dets_xyxy)), dtype=np.float32)
    D = np.zeros((len(tracks_xyxy), len(dets_xyxy)), dtype=np.float32)
    for i, t in enumerate(tracks_xyxy):
        for j, d in enumerate(dets_xyxy):
            D[i, j] = 1.0 - iou_xyxy(t, d)
    return D

def hungarian_assign(cost: np.ndarray, cost_thr: float) -> Tuple[List[Tuple[int,int]], List[int], List[int]]:
    """
    Возвращает matches, unmatched_tracks, unmatched_dets.
    cost: меньше = лучше
    """
    n_t, n_d = cost.shape if cost.ndim == 2 else (0, 0)
    if n_t == 0:
        return [], [], list(range(n_d))
    if n_d == 0:
        return [], list(range(n_t)), []

    r, c = linear_sum_assignment(cost)
    matches = []
    unmatched_t = set(range(n_t))
    unmatched_d = set(range(n_d))

    for ri, ci in zip(r, c):
        if cost[ri, ci] <= cost_thr:
            matches.append((int(ri), int(ci)))
            unmatched_t.discard(int(ri))
            unmatched_d.discard(int(ci))

    return matches, sorted(unmatched_t), sorted(unmatched_d)