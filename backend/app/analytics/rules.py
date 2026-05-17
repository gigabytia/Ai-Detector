from typing import Dict, List, Any
from ..config import SETTINGS

class EventEmitter:
    """
    Анти-спам:
    - cooldown по (camera_id + event_type)
    - hand_raised только по rising edge (старт поднятия руки)
    - lying только если лежит N секунд
    """
    def __init__(self):
        self._last_event_ts: Dict[str, float] = {}
        self._lying_since_by_track: Dict[int, float] = {}
        self._hand_prev_by_track: Dict[int, bool] = {}

    def _can_emit(self, key: str, now: float) -> bool:
        last = self._last_event_ts.get(key, 0.0)
        if (now - last) >= SETTINGS.EVENT_COOLDOWN_SEC:
            self._last_event_ts[key] = now
            return True
        return False

    def update(self, camera_id: int, detections: List[Dict[str, Any]], now: float) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []

        # hand_raised: rising edge + cooldown по камере
        for det in detections:
            tid = int(det["track_id"])
            has_hand = bool(det.get("has_hand_raised", False))
            prev = bool(self._hand_prev_by_track.get(tid, False))

            if has_hand and not prev:
                key = f"{camera_id}:hand_raised"
                if self._can_emit(key, now):
                    events.append({
                        "camera_id": camera_id,
                        "track_id": tid,
                        "event_type": "hand_raised",
                        "severity": "info",
                        "ts": now,
                        "text": f"ID {tid}: поднята рука",
                    })

            self._hand_prev_by_track[tid] = has_hand

        # lying: N секунд + cooldown по камере
        for det in detections:
            tid = int(det["track_id"])
            base_pose = det.get("base_pose", det.get("pose", "unknown"))

            if base_pose == "lying":
                if tid not in self._lying_since_by_track:
                    self._lying_since_by_track[tid] = now
                dur = now - self._lying_since_by_track[tid]
                if dur >= SETTINGS.LYING_ALERT_AFTER_SEC:
                    key = f"{camera_id}:person_lying"
                    if self._can_emit(key, now):
                        events.append({
                            "camera_id": camera_id,
                            "track_id": tid,
                            "event_type": "person_lying",
                            "severity": "warn",
                            "ts": now,
                            "text": f"ID {tid}: человек лежит ({dur:.1f} c)",
                        })
            else:
                self._lying_since_by_track.pop(tid, None)

        return events