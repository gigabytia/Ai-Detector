"""
Утилиты для визуализации результатов трекинга и классификации поз.
"""
import cv2
import numpy as np
from typing import List, Tuple, Dict, Optional
from config import PoseConfig
import csv
import os
from datetime import datetime


class PoseVisualizer:
    """Отрисовка результатов на кадре."""

    def __init__(self, config: PoseConfig = None):
        self.config = config or PoseConfig()

    def draw_results(
        self,
        frame: np.ndarray,
        bboxes: np.ndarray,
        track_ids: List[int],
        keypoints_list: np.ndarray,
        confidences_list: np.ndarray,
        poses: List[Tuple[str, Dict[str, float]]],
    ) -> np.ndarray:
        """
        Отрисовывает все результаты на кадре.

        Args:
            frame:            исходный кадр BGR
            bboxes:           (N, 4) — x1, y1, x2, y2
            track_ids:        список N track-ID
            keypoints_list:   (N, 17, 2) координаты
            confidences_list: (N, 17) уверенности
            poses:            список (pose_label, scores)

        Returns:
            Кадр с отрисовкой
        """
        annotated = frame.copy()

        for i in range(len(bboxes)):
            bbox = bboxes[i]
            track_id = track_ids[i] if i < len(track_ids) else -1
            kps = keypoints_list[i]
            confs = confidences_list[i]
            pose_label, pose_scores = poses[i]

            color = self.config.POSE_COLORS.get(pose_label, (128, 128, 128))

            # Bounding box
            self._draw_bbox(annotated, bbox, track_id, pose_label, color)

            # Скелет
            self._draw_skeleton(annotated, kps, confs)

            # Ключевые точки
            self._draw_keypoints(annotated, kps, confs)

            # Метка позы
            self._draw_pose_label(annotated, bbox, track_id, pose_label, color)

        # Счётчики
        self._draw_counters(annotated, poses)

        return annotated

    def _draw_bbox(
        self,
        frame: np.ndarray,
        bbox: np.ndarray,
        track_id: int,
        pose: str,
        color: Tuple[int, int, int],
    ):
        """Рисует bounding box."""
        x1, y1, x2, y2 = map(int, bbox)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, self.config.BBOX_THICKNESS)

    def _draw_skeleton(
        self,
        frame: np.ndarray,
        keypoints: np.ndarray,
        confidences: np.ndarray,
    ):
        """Рисует скелет (соединения между ключевыми точками)."""
        thr = self.config.KEYPOINT_CONFIDENCE_THRESHOLD

        for i, j in self.config.SKELETON_CONNECTIONS:
            if confidences[i] > thr and confidences[j] > thr:
                pt1 = tuple(map(int, keypoints[i]))
                pt2 = tuple(map(int, keypoints[j]))
                cv2.line(frame, pt1, pt2, self.config.SKELETON_COLOR, 2)

    def _draw_keypoints(
        self,
        frame: np.ndarray,
        keypoints: np.ndarray,
        confidences: np.ndarray,
    ):
        """Рисует ключевые точки."""
        thr = self.config.KEYPOINT_CONFIDENCE_THRESHOLD

        for idx in range(17):
            if confidences[idx] > thr:
                x, y = int(keypoints[idx][0]), int(keypoints[idx][1])
                cv2.circle(
                    frame, (x, y),
                    self.config.KEYPOINT_RADIUS,
                    self.config.KEYPOINT_COLOR,
                    -1,
                )

    def _draw_pose_label(
        self,
        frame: np.ndarray,
        bbox: np.ndarray,
        track_id: int,
        pose: str,
        color: Tuple[int, int, int],
    ):
        """Рисует подпись с ID и позой."""
        x1, y1 = int(bbox[0]), int(bbox[1])

        # Перевод названий поз на русский
        pose_names_ru = {
            "standing": "Стоит",
            "sitting": "Сидит",
            "hand_raised": "Рука поднята",
            "unknown": "Неизвестно",
        }

        label = f"ID:{track_id} {pose_names_ru.get(pose, pose)}"

        # Фон для текста
        (text_w, text_h), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX,
            self.config.TEXT_SCALE, self.config.TEXT_THICKNESS,
        )

        cv2.rectangle(
            frame,
            (x1, y1 - text_h - baseline - 10),
            (x1 + text_w + 5, y1),
            color, -1,
        )

        cv2.putText(
            frame, label,
            (x1 + 2, y1 - baseline - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            self.config.TEXT_SCALE,
            (255, 255, 255),
            self.config.TEXT_THICKNESS,
        )

    def _draw_counters(
        self,
        frame: np.ndarray,
        poses: List[Tuple[str, Dict[str, float]]],
    ):
        """Рисует счётчики поз в углу кадра."""
        counts = {"standing": 0, "sitting": 0, "hand_raised": 0, "unknown": 0}
        for pose_label, _ in poses:
            counts[pose_label] = counts.get(pose_label, 0) + 1

        pose_names_ru = {
            "standing": "Стоят",
            "sitting": "Сидят",
            "hand_raised": "Рука поднята",
        }

        y_offset = 30
        total = sum(counts.values())

        # Фон панели
        cv2.rectangle(frame, (5, 5), (280, 30 + len(pose_names_ru) * 30 + 30), (0, 0, 0), -1)
        cv2.putText(
            frame, f"Всего людей: {total}",
            (10, y_offset),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2,
        )
        y_offset += 30

        for key, name in pose_names_ru.items():
            color = self.config.POSE_COLORS[key]
            text = f"{name}: {counts.get(key, 0)}"
            cv2.putText(
                frame, text,
                (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
            )
            y_offset += 30


class PoseLogger:
    """Логирование результатов трекинга в CSV."""

    def __init__(self, log_file: str = "pose_tracking_log.csv"):
        self.log_file = log_file
        self._initialized = False

    def _init_file(self):
        """Создаёт файл с заголовками."""
        with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'frame_number', 'track_id',
                'pose', 'bbox_x1', 'bbox_y1', 'bbox_x2', 'bbox_y2',
                'confidence_standing', 'confidence_sitting', 'confidence_hand_raised',
            ])
        self._initialized = True

    def log(
        self,
        frame_number: int,
        track_ids: List[int],
        bboxes: np.ndarray,
        poses: List[Tuple[str, Dict[str, float]]],
    ):
        """Записывает данные кадра в лог."""
        if not self._initialized:
            self._init_file()

        timestamp = datetime.now().isoformat()

        with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for i, (pose_label, scores) in enumerate(poses):
                tid = track_ids[i] if i < len(track_ids) else -1
                bb = bboxes[i] if i < len(bboxes) else [0, 0, 0, 0]
                writer.writerow([
                    timestamp, frame_number, tid, pose_label,
                    f"{bb[0]:.1f}", f"{bb[1]:.1f}",
                    f"{bb[2]:.1f}", f"{bb[3]:.1f}",
                    f"{scores.get('standing', 0):.2f}",
                    f"{scores.get('sitting', 0):.2f}",
                    f"{scores.get('hand_raised', 0):.2f}",
                ])

    def close(self):
        """Формальное закрытие логгера."""
        if self._initialized and os.path.exists(self.log_file):
            size_kb = os.path.getsize(self.log_file) / 1024
            print(f"[INFO] CSV лог сохранён: {self.log_file} ({size_kb:.1f} KB)")


class FPSCounter:
    """Счётчик FPS."""

    def __init__(self, avg_frames: int = 30):
        self._times = []
        self._avg_frames = avg_frames

    def tick(self) -> float:
        """Вызывать каждый кадр. Возвращает текущий FPS."""
        import time
        now = time.time()
        self._times.append(now)

        if len(self._times) > self._avg_frames:
            self._times.pop(0)

        if len(self._times) < 2:
            return 0.0

        elapsed = self._times[-1] - self._times[0]
        if elapsed == 0:
            return 0.0

        return (len(self._times) - 1) / elapsed

    def draw(self, frame: np.ndarray) -> np.ndarray:
        """Отрисовывает FPS на кадре."""
        fps = self.tick()
        h, w = frame.shape[:2]
        text = f"FPS: {fps:.1f}"
        cv2.putText(
            frame, text,
            (w - 180, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
        )
        return frame