# backend/app/pipeline/events.py
from typing import Dict, List, Any, Tuple
from ..config import SETTINGS


class EventEmitter:
    def __init__(self):
        self._last: Dict[Tuple[int, int, str], float] = {}

    def _can(self, camera_id: int, track_id: int, event_type: str, now: float) -> bool:
        key = (int(camera_id), int(track_id), str(event_type))
        last = self._last.get(key, 0.0)
        if (now - last) >= SETTINGS.EVENT_COOLDOWN_SEC:
            self._last[key] = now
            return True
        return False

    def carry_out_event(
        self, camera_id: int, track_id: int, now: float,
        obj_label: str, payload: dict,
    ) -> List[Dict[str, Any]]:
        if not self._can(camera_id, track_id, "carry_out", now):
            return []
        return [{
            "camera_id": int(camera_id),
            "track_id": int(track_id),
            "event_type": "carry_out",
            "severity": "warn",
            "ts": float(now),
            "text": f"ID {track_id}: вынос через выходную зону (объект: {obj_label})",
            "payload": payload,
        }]

    def exit_zone_event(
        self, camera_id: int, track_id: int, now: float,
    ) -> List[Dict[str, Any]]:
        if not self._can(camera_id, track_id, "enter_exit_zone", now):
            return []
        return [{
            "camera_id": int(camera_id),
            "track_id": int(track_id),
            "event_type": "enter_exit_zone",
            "severity": "info",
            "ts": float(now),
            "text": f"ID {track_id}: человек в опасной зоне",
            "payload": {},
        }]

    def line_cross_event(
        self, camera_id: int, track_id: int, now: float,
        carrying: bool = False,
    ) -> List[Dict[str, Any]]:
        event_type = "line_cross_carry" if carrying else "line_cross"
        if not self._can(camera_id, track_id, event_type, now):
            return []
        severity = "warn" if carrying else "info"
        text = f"ID {track_id}: пересёк линию выхода"
        if carrying:
            text += " с грузом"
        return [{
            "camera_id": int(camera_id),
            "track_id": int(track_id),
            "event_type": event_type,
            "severity": severity,
            "ts": float(now),
            "text": text,
            "payload": {"carrying": carrying},
        }]

    def loitering_event(
        self, camera_id: int, track_id: int, now: float,
        dwell_sec: float,
    ) -> List[Dict[str, Any]]:
        if not self._can(camera_id, track_id, "loitering", now):
            return []
        return [{
            "camera_id": int(camera_id),
            "track_id": int(track_id),
            "event_type": "loitering",
            "severity": "warn",
            "ts": float(now),
            "text": f"ID {track_id}: долго в зоне ({dwell_sec:.0f} сек)",
            "payload": {"dwell_sec": dwell_sec},
        }]