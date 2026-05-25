from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import numpy as np

from .kalman_filter import KalmanXYAH, tlwh_to_xyah, xyah_to_tlwh
from .matching import iou_distance, hungarian_assign

@dataclass
class Track:
    track_id: int
    tlwh: np.ndarray
    score: float
    cls_id: int
    cls_name: str

    kf: KalmanXYAH = field(default_factory=KalmanXYAH)
    age: int = 0
    time_since_update: int = 0
    hits: int = 0
    active: bool = True

    def __post_init__(self):
        self.kf.initiate(tlwh_to_xyah(self.tlwh))

    def predict(self):
        self.kf.predict()
        self.age += 1
        self.time_since_update += 1

    def update(self, tlwh: np.ndarray, score: float):
        self.tlwh = tlwh.astype(np.float32)
        self.kf.update(tlwh_to_xyah(self.tlwh))
        self.score = float(score)
        self.time_since_update = 0
        self.hits += 1

    def to_tlwh(self) -> np.ndarray:
        m = self.kf.mean
        return xyah_to_tlwh(m[:4])

    def to_xyxy(self) -> np.ndarray:
        x, y, w, h = self.to_tlwh()
        return np.array([x, y, x+w, y+h], dtype=np.float32)

class ByteTracker:
    """
    Упрощённый ByteTrack:
      - Kalman predict
      - Hungarian по IoU distance
      - удаление по max_age
    """
    def __init__(self, track_thresh: float = 0.25, match_iou_thr: float = 0.7, max_age: int = 30):
        self.track_thresh = float(track_thresh)
        self.match_iou_thr = float(match_iou_thr)
        self.max_age = int(max_age)
        self._next_id = 1
        self.tracks: List[Track] = []

    def _new_track(self, tlwh: np.ndarray, score: float, cls_id: int, cls_name: str) -> Track:
        tr = Track(
            track_id=self._next_id,
            tlwh=tlwh.astype(np.float32),
            score=float(score),
            cls_id=int(cls_id),
            cls_name=str(cls_name),
        )
        self._next_id += 1
        tr.hits = 1
        return tr

    def update(self, dets_xyxy: np.ndarray, det_scores: np.ndarray, det_cls: np.ndarray, det_names: List[str]) -> List[Track]:
        # predict
        for t in self.tracks:
            t.predict()

        if dets_xyxy is None or len(dets_xyxy) == 0:
            # only age-out
            self.tracks = [t for t in self.tracks if t.time_since_update <= self.max_age]
            return [t for t in self.tracks if t.active and t.time_since_update == 0]

        # convert dets to tlwh
        dets_xyxy = dets_xyxy.astype(np.float32)
        tlwhs = np.zeros((len(dets_xyxy), 4), dtype=np.float32)
        tlwhs[:,0] = dets_xyxy[:,0]
        tlwhs[:,1] = dets_xyxy[:,1]
        tlwhs[:,2] = dets_xyxy[:,2] - dets_xyxy[:,0]
        tlwhs[:,3] = dets_xyxy[:,3] - dets_xyxy[:,1]

        active_tracks = [t for t in self.tracks if t.active]
        tracks_xyxy = [t.to_xyxy() for t in active_tracks]

        cost = iou_distance(tracks_xyxy, list(dets_xyxy))
        # cost_thr: 1 - iou >= (1 - thr) => iou >= thr
        cost_thr = 1.0 - self.match_iou_thr

        matches, um_t, um_d = hungarian_assign(cost, cost_thr=cost_thr)

        # update matched
        for ti, di in matches:
            t = active_tracks[ti]
            t.update(tlwhs[di], float(det_scores[di]))

        # create new tracks for unmatched detections above thresh
        for di in um_d:
            sc = float(det_scores[di])
            if sc < self.track_thresh:
                continue
            cls_id = int(det_cls[di])
            cls_name = det_names[di] if di < len(det_names) else str(cls_id)
            self.tracks.append(self._new_track(tlwhs[di], sc, cls_id, cls_name))

        # remove old
        self.tracks = [t for t in self.tracks if t.time_since_update <= self.max_age]

        # return tracks updated in this frame
        return [t for t in self.tracks if t.active and t.time_since_update == 0]