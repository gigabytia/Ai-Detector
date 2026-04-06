"""
Сбор и агрегация аналитики по результатам трекинга поз.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from collections import Counter, defaultdict
import os
import json


@dataclass
class FrameRecord:
    frame_number: int
    timestamp_sec: float
    total_people: int
    detections: List[Dict[str, Any]] = field(default_factory=list)


class AnalyticsCollector:
    """
    Сборщик аналитики по кадрам, трекам и событиям.

    Накапливает:
    - временной ряд по кадрам
    - историю по каждому track_id
    - события поднятия руки
    """

    def __init__(
        self,
        source: str,
        fps: float,
        frame_width: int,
        frame_height: int,
    ):
        self.source = str(source)
        self.fps = float(fps or 30.0)
        self.frame_width = int(frame_width)
        self.frame_height = int(frame_height)

        self.frames: List[FrameRecord] = []
        self.track_history: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        self.events: List[Dict[str, Any]] = []

        # Храним последнюю позу по треку, чтобы фиксировать начало событий
        self._last_pose_by_track: Dict[int, Optional[str]] = {}

    def add_frame(self, frame_number: int, detections: List[Dict[str, Any]]):
        """
        Добавляет аналитику по одному кадру.

        Args:
            frame_number: номер кадра
            detections: список детекций из process_frame()
        """
        timestamp_sec = frame_number / self.fps
        total_people = len(detections)
        frame_detections = []

        for det in detections:
            track_id = int(det["track_id"])
            bbox = det["bbox"]
            pose = det["pose"]

            x1, y1, x2, y2 = map(float, bbox)
            center_x = (x1 + x2) / 2.0
            center_y = (y1 + y2) / 2.0
            bbox_w = x2 - x1
            bbox_h = y2 - y1

            item = {
                "frame_number": frame_number,
                "timestamp_sec": timestamp_sec,
                "track_id": track_id,
                "pose": pose,
                "bbox_x1": x1,
                "bbox_y1": y1,
                "bbox_x2": x2,
                "bbox_y2": y2,
                "center_x": center_x,
                "center_y": center_y,
                "bbox_w": bbox_w,
                "bbox_h": bbox_h,
            }

            frame_detections.append(item)
            self.track_history[track_id].append(item)

            prev_pose = self._last_pose_by_track.get(track_id)

            # Фиксируем только момент начала события "поднята рука"
            if pose == "hand_raised" and prev_pose != "hand_raised":
                self.events.append({
                    "event_type": "hand_raised_start",
                    "track_id": track_id,
                    "frame_number": frame_number,
                    "timestamp_sec": timestamp_sec,
                    "center_x": center_x,
                    "center_y": center_y,
                })

            self._last_pose_by_track[track_id] = pose

        self.frames.append(FrameRecord(
            frame_number=frame_number,
            timestamp_sec=timestamp_sec,
            total_people=total_people,
            detections=frame_detections,
        ))

    def finalize(self, status: str = "completed") -> Dict[str, Any]:
        """
        Формирует итоговую сводку для отчёта.
        """
        total_frames = len(self.frames)
        processed_duration_sec = total_frames / self.fps if total_frames else 0.0

        people_counts = [f.total_people for f in self.frames]
        avg_people = sum(people_counts) / len(people_counts) if people_counts else 0.0
        max_people = max(people_counts) if people_counts else 0

        unique_tracks = sorted(self.track_history.keys())

        # Суммарные детекции по позам
        pose_counter = Counter()
        for frame in self.frames:
            for det in frame.detections:
                pose_counter[det["pose"]] += 1

        # Таймлайн по кадрам
        timeline = []
        for frame in self.frames:
            frame_pose_counter = Counter(det["pose"] for det in frame.detections)
            timeline.append({
                "frame_number": frame.frame_number,
                "timestamp_sec": frame.timestamp_sec,
                "total_people": frame.total_people,
                "standing": frame_pose_counter.get("standing", 0),
                "sitting": frame_pose_counter.get("sitting", 0),
                "hand_raised": frame_pose_counter.get("hand_raised", 0),
                "unknown": frame_pose_counter.get("unknown", 0),
            })

        # Сводка по track_id
        track_summary = []
        for track_id, records in self.track_history.items():
            first_seen = records[0]["timestamp_sec"]
            last_seen = records[-1]["timestamp_sec"]
            duration_sec = max(0.0, last_seen - first_seen)

            poses = [r["pose"] for r in records]
            dominant_pose = Counter(poses).most_common(1)[0][0]

            hand_raise_events = sum(
                1 for e in self.events
                if e["event_type"] == "hand_raised_start" and e["track_id"] == track_id
            )

            avg_center_x = sum(r["center_x"] for r in records) / len(records)
            avg_center_y = sum(r["center_y"] for r in records) / len(records)

            min_x = min(r["center_x"] for r in records)
            max_x = max(r["center_x"] for r in records)
            min_y = min(r["center_y"] for r in records)
            max_y = max(r["center_y"] for r in records)

            track_summary.append({
                "track_id": track_id,
                "first_seen_sec": first_seen,
                "last_seen_sec": last_seen,
                "duration_sec": duration_sec,
                "frames_seen": len(records),
                "dominant_pose": dominant_pose,
                "hand_raise_events": hand_raise_events,
                "avg_center_x": avg_center_x,
                "avg_center_y": avg_center_y,
                "min_center_x": min_x,
                "max_center_x": max_x,
                "min_center_y": min_y,
                "max_center_y": max_y,
            })

        track_summary.sort(key=lambda x: x["track_id"])

        summary = {
            "meta": {
                "source": self.source,
                "fps": self.fps,
                "frame_width": self.frame_width,
                "frame_height": self.frame_height,
                "status": status,
                "total_frames_processed": total_frames,
                "processed_duration_sec": processed_duration_sec,
            },
            "kpi": {
                "unique_people": len(unique_tracks),
                "avg_people_per_frame": avg_people,
                "max_people_in_frame": max_people,
                "hand_raise_events": len([
                    e for e in self.events
                    if e["event_type"] == "hand_raised_start"
                ]),
                "standing_detections": pose_counter.get("standing", 0),
                "sitting_detections": pose_counter.get("sitting", 0),
                "hand_raised_detections": pose_counter.get("hand_raised", 0),
                "unknown_detections": pose_counter.get("unknown", 0),
            },
            "timeline": timeline,
            "track_summary": track_summary,
            "events": self.events,
            "frames": [
                {
                    "frame_number": f.frame_number,
                    "timestamp_sec": f.timestamp_sec,
                    "total_people": f.total_people,
                    "detections": f.detections,
                }
                for f in self.frames
            ],
        }

        return summary

    def save_json(self, summary: Dict[str, Any], output_path: str):
        """
        Сохраняет summary в JSON.
        """
        directory = os.path.dirname(output_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)