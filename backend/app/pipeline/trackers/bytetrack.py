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
        return np.array([x, y, x + w, y + h], dtype=np.float32)


class ByteTracker:
    """
    ByteTrack с двухэтапным сопоставлением:
      - Этап 1: high-conf детекции → активные треки
      - Этап 2: low-conf детекции → потерянные треки
      - min_hits: трек показывается только после N подтверждений (убирает мигание)
      - grace: трек держится N кадров без детекции (убирает пропадание боксов)
    """
    def __init__(
        self,
        track_thresh: float = 0.25,
        match_iou_thr: float = 0.35,
        max_age: int = 30,
        min_hits: int = 2,
        grace: int = 3,
    ):
        self.track_thresh = float(track_thresh)
        self.match_iou_thr = float(match_iou_thr)
        self.max_age = int(max_age)
        self.min_hits = int(min_hits)
        self.grace = int(grace)
        self._next_id = 1
        self.tracks: List[Track] = []

    def _new_track(self, tlwh, score, cls_id, cls_name) -> Track:
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

    def _confirmed(self) -> List[Track]:
        """Треки показываемые пользователю: подтверждены И недавно виданы."""
        return [
            t for t in self.tracks
            if t.hits >= self.min_hits and t.time_since_update <= self.grace
        ]

    def update(
        self,
        dets_xyxy: np.ndarray,
        det_scores: np.ndarray,
        det_cls: np.ndarray,
        det_names: List[str],
    ) -> List[Track]:

        # Kalman predict для всех треков
        for t in self.tracks:
            t.predict()

        if dets_xyxy is None or len(dets_xyxy) == 0:
            self.tracks = [t for t in self.tracks if t.time_since_update <= self.max_age]
            return self._confirmed()

        dets_xyxy = dets_xyxy.astype(np.float32)
        tlwhs = np.zeros((len(dets_xyxy), 4), dtype=np.float32)
        tlwhs[:, 0] = dets_xyxy[:, 0]
        tlwhs[:, 1] = dets_xyxy[:, 1]
        tlwhs[:, 2] = dets_xyxy[:, 2] - dets_xyxy[:, 0]
        tlwhs[:, 3] = dets_xyxy[:, 3] - dets_xyxy[:, 1]

        # Разделяем на high/low confidence
        high_idx = [i for i, s in enumerate(det_scores) if float(s) >= self.track_thresh]
        low_idx  = [i for i, s in enumerate(det_scores) if float(s) < self.track_thresh]

        # ── Этап 1: high-conf → активные треки ────────────────────────────
        active_tracks = [t for t in self.tracks if t.time_since_update <= 1]
        lost_tracks   = [t for t in self.tracks if t.time_since_update > 1]

        unmatched_high = list(high_idx)
        unmatched_active_idx = list(range(len(active_tracks)))

        if active_tracks and high_idx:
            hi_dets = dets_xyxy[high_idx]
            cost = iou_distance([t.to_xyxy() for t in active_tracks], list(hi_dets))
            matches, um_t, um_d_local = hungarian_assign(cost, cost_thr=1.0 - self.match_iou_thr)

            for ti, di_local in matches:
                di = high_idx[di_local]
                active_tracks[ti].update(tlwhs[di], float(det_scores[di]))

            unmatched_high = [high_idx[i] for i in um_d_local]
            unmatched_active_idx = list(um_t)

        # ── Этап 2: low-conf → незасопоставленные активные треки ──────────
        if unmatched_active_idx and low_idx:
            um_active = [active_tracks[i] for i in unmatched_active_idx]
            lo_dets = dets_xyxy[low_idx]
            cost2 = iou_distance([t.to_xyxy() for t in um_active], list(lo_dets))
            matches2, um_t2, _ = hungarian_assign(cost2, cost_thr=1.0 - self.match_iou_thr * 0.6)

            for ti, di_local in matches2:
                di = low_idx[di_local]
                um_active[ti].update(tlwhs[di], float(det_scores[di]))

            unmatched_active_idx = [unmatched_active_idx[i] for i in um_t2]

        # ── Этап 3: незасопоставленные high-conf → потерянные треки ────────
        still_unmatched_high = list(unmatched_high)
        if lost_tracks and still_unmatched_high:
            hi2_dets = dets_xyxy[still_unmatched_high]
            cost3 = iou_distance([t.to_xyxy() for t in lost_tracks], list(hi2_dets))
            matches3, _, um_d3_local = hungarian_assign(cost3, cost_thr=1.0 - self.match_iou_thr * 0.5)

            for ti, di_local in matches3:
                di = still_unmatched_high[di_local]
                lost_tracks[ti].update(tlwhs[di], float(det_scores[di]))

            still_unmatched_high = [still_unmatched_high[i] for i in um_d3_local]

        # ── Создаём новые треки для оставшихся high-conf детекций ──────────
        for di in still_unmatched_high:
            sc = float(det_scores[di])
            cls_id = int(det_cls[di])
            cls_name = det_names[di] if di < len(det_names) else str(cls_id)
            self.tracks.append(self._new_track(tlwhs[di], sc, cls_id, cls_name))

        # Удаляем старые треки
        self.tracks = [t for t in self.tracks if t.time_since_update <= self.max_age]

        return self._confirmed()
