"""
Основной модуль трекинга людей с определением поз.
Связывает YOLOv8-pose с классификатором поз.
"""
import numpy as np
import cv2
from typing import List, Tuple, Dict, Optional
from ultralytics import YOLO

from config import PoseConfig
from pose_classifier import PoseClassifier
from utils import PoseVisualizer, PoseLogger, FPSCounter


class PoseTracker:
    """
    Трекер людей с определением поз:
    - Детекция и трекинг через YOLOv8-pose
    - Классификация поз: стоит, сидит, рука поднята
    - Визуализация и логирование
    """

    def __init__(self, config: PoseConfig = None):
        self.config = config or PoseConfig()

        # Загрузка модели YOLOv8-pose
        print(f"[INFO] Загрузка модели: {self.config.MODEL_NAME}")
        self.model = YOLO(self.config.MODEL_NAME)
        print("[INFO] Модель загружена успешно")

        # Компоненты
        self.classifier = PoseClassifier(self.config)
        self.visualizer = PoseVisualizer(self.config)
        self.logger = PoseLogger(self.config.LOG_FILE) if self.config.SAVE_LOGS else None
        self.fps_counter = FPSCounter()

        # Состояние
        self.frame_count = 0
        self._active_tracks = set()

    def process_frame(
        self,
        frame: np.ndarray,
        visualize: bool = True,
    ) -> Tuple[np.ndarray, List[Dict]]:
        """
        Обрабатывает один кадр.

        Args:
            frame:      кадр BGR
            visualize:  нужно ли рисовать на кадре

        Returns:
            (annotated_frame, detections)
            detections — список словарей:
                {
                    "track_id": int,
                    "bbox": (x1, y1, x2, y2),
                    "pose": str,
                    "scores": dict,
                    "keypoints": np.ndarray,
                }
        """
        self.frame_count += 1

        # ── 1. Детекция + трекинг ───────────────────────────
        results = self.model.track(
            frame,
            persist=True,
            conf=self.config.DETECTION_CONFIDENCE,
            iou=self.config.IOU_THRESHOLD,
            tracker=self.config.TRACKER_TYPE,
            verbose=False,
        )

        # ── 2. Извлечение данных ────────────────────────────
        detections = []
        result = results[0]

        if result.boxes is None or len(result.boxes) == 0:
            if visualize:
                frame = self.fps_counter.draw(frame)
            return frame, detections

        # Bounding boxes
        bboxes = result.boxes.xyxy.cpu().numpy()  # (N, 4)

        # Track IDs
        if result.boxes.id is not None:
            track_ids = result.boxes.id.cpu().numpy().astype(int).tolist()
        else:
            track_ids = list(range(len(bboxes)))

        # Ключевые точки
        if result.keypoints is not None:
            kp_data = result.keypoints.data.cpu().numpy()  # (N, 17, 3)
            keypoints_xy = kp_data[:, :, :2]                # (N, 17, 2)
            keypoints_conf = kp_data[:, :, 2]                # (N, 17)
        else:
            # Нет ключевых точек — невозможно классифицировать
            if visualize:
                frame = self.fps_counter.draw(frame)
            return frame, detections

        # ── 3. Классификация поз ────────────────────────────
        poses = self.classifier.classify_multiple(
            keypoints_xy, keypoints_conf, track_ids, bboxes
        )

        # ── 4. Формирование результатов ─────────────────────
        for i in range(len(bboxes)):
            detections.append({
                "track_id": track_ids[i],
                "bbox": tuple(bboxes[i]),
                "pose": poses[i][0],
                "scores": poses[i][1],
                "keypoints": keypoints_xy[i],
                "keypoint_conf": keypoints_conf[i],
            })

        # ── 5. Обновление активных треков ────────────────────
        current_ids = set(track_ids)
        lost_ids = self._active_tracks - current_ids
        for lost_id in lost_ids:
            self.classifier.clear_track(lost_id)
        self._active_tracks = current_ids

        # ── 6. Логирование ──────────────────────────────────
        if self.logger:
            self.logger.log(self.frame_count, track_ids, bboxes, poses)

        # ── 7. Визуализация ─────────────────────────────────
        if visualize:
            frame = self.visualizer.draw_results(
                frame, bboxes, track_ids,
                keypoints_xy, keypoints_conf, poses,
            )
            frame = self.fps_counter.draw(frame)

        return frame, detections

    def process_video(
        self,
        source,
        show: bool = True,
        save_path: Optional[str] = None,
    ):
        """
        Обрабатывает видео (файл или камеру).

        Args:
            source:    путь к файлу или ID камеры (0, 1, ...)
            show:      показывать окно с результатами
            save_path: путь для сохранения видео (или None)
        """
        cap = cv2.VideoCapture(source)

        if not cap.isOpened():
            raise RuntimeError(f"Не удалось открыть источник: {source}")

        # Параметры видео
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30

        print(f"[INFO] Видео: {width}x{height} @ {fps} FPS")

        # Запись видео
        writer = None
        if save_path:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(save_path, fourcc, fps, (width, height))
            print(f"[INFO] Запись в: {save_path}")

        print("[INFO] Начинаем обработку. Нажмите 'q' для выхода.")
        print("=" * 50)

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("[INFO] Конец видео")
                    break

                # Обработка кадра
                annotated, detections = self.process_frame(frame, visualize=True)

                # Вывод информации в консоль каждые 30 кадров
                if self.frame_count % 30 == 0:
                    poses_summary = {}
                    for d in detections:
                        p = d["pose"]
                        poses_summary[p] = poses_summary.get(p, 0) + 1
                    print(
                        f"  Кадр {self.frame_count}: "
                        f"людей={len(detections)}, "
                        f"позы={poses_summary}"
                    )

                # Показ
                if show:
                    cv2.imshow("Pose Tracker", annotated)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        print("[INFO] Остановлено пользователем")
                        break
                    elif key == ord('s'):
                        # Скриншот
                        screenshot_path = f"screenshot_{self.frame_count}.jpg"
                        cv2.imwrite(screenshot_path, annotated)
                        print(f"[INFO] Скриншот сохранён: {screenshot_path}")

                # Запись
                if writer:
                    writer.write(annotated)

        finally:
            cap.release()
            if writer:
                writer.release()
            cv2.destroyAllWindows()
            print(f"[INFO] Обработано кадров: {self.frame_count}")

    def process_image(
        self,
        image_path: str,
        save_path: Optional[str] = None,
        show: bool = True,
    ) -> Tuple[np.ndarray, List[Dict]]:
        """
        Обрабатывает одно изображение.

        Args:
            image_path: путь к изображению
            save_path:  путь для сохранения результата
            show:       показать результат

        Returns:
            (annotated_frame, detections)
        """
        frame = cv2.imread(image_path)
        if frame is None:
            raise FileNotFoundError(f"Не удалось загрузить: {image_path}")

        annotated, detections = self.process_frame(frame, visualize=True)

        if save_path:
            cv2.imwrite(save_path, annotated)
            print(f"[INFO] Результат сохранён: {save_path}")

        if show:
            cv2.imshow("Pose Detection", annotated)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        return annotated, detections

    def get_statistics(self, detections: List[Dict]) -> Dict:
        """Возвращает статистику по текущим детекциям."""
        stats = {
            "total_people": len(detections),
            "standing": 0,
            "sitting": 0,
            "hand_raised": 0,
            "unknown": 0,
            "track_ids": [],
        }

        for d in detections:
            pose = d["pose"]
            stats[pose] = stats.get(pose, 0) + 1
            stats["track_ids"].append(d["track_id"])

        return stats