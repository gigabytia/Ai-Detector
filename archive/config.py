"""
Конфигурация проекта для трекинга поз.
"""
from dataclasses import dataclass, field
from typing import Tuple, Dict


@dataclass
class PoseConfig:
    """Конфигурация для определения поз."""

    # ──────────────────────────────────────────────
    # Индексы ключевых точек COCO (YOLOv8-pose)
    # ──────────────────────────────────────────────
    # 0:  нос
    # 1:  левый глаз        2:  правый глаз
    # 3:  левое ухо         4:  правое ухо
    # 5:  левое плечо       6:  правое плечо
    # 7:  левый локоть       8:  правый локоть
    # 9:  левое запястье    10: правое запястье
    # 11: левое бедро       12: правое бедро
    # 13: левое колено      14: правое колено
    # 15: левая лодыжка     16: правая лодыжка

    KEYPOINT_NAMES: Dict[int, str] = field(default_factory=lambda: {
        0: "nose",
        1: "left_eye", 2: "right_eye",
        3: "left_ear", 4: "right_ear",
        5: "left_shoulder", 6: "right_shoulder",
        7: "left_elbow", 8: "right_elbow",
        9: "left_wrist", 10: "right_wrist",
        11: "left_hip", 12: "right_hip",
        13: "left_knee", 14: "right_knee",
        15: "left_ankle", 16: "right_ankle",
    })

    # ──────────────────────────────────────────────
    # Пороги для классификации поз
    # ──────────────────────────────────────────────

    # Минимальная уверенность ключевой точки
    KEYPOINT_CONFIDENCE_THRESHOLD: float = 0.3

    # Поднятая рука: запястье выше плеча на N пикселей
    RAISED_HAND_OFFSET: float = 50.0

    # Сидит: отношение (бедро_Y - колено_Y) к длине торса
    SITTING_HIP_KNEE_RATIO: float = 0.3

    # Угол колена для определения "сидит" (в градусах)
    SITTING_KNEE_ANGLE_MAX: float = 130.0
    SITTING_KNEE_ANGLE_MIN: float = 50.0

    # Стоит: отношение высоты ног к общей высоте тела
    STANDING_LEG_RATIO_MIN: float = 0.4

    # ──────────────────────────────────────────────
    # Настройки модели
    # ──────────────────────────────────────────────
    MODEL_NAME: str = "yolov8n-pose.pt"  # nano-версия для скорости
    # Альтернативы: yolov8s-pose.pt, yolov8m-pose.pt, yolov8l-pose.pt, yolov8x-pose.pt

    DETECTION_CONFIDENCE: float = 0.5
    IOU_THRESHOLD: float = 0.45

    # ──────────────────────────────────────────────
    # Настройки трекера
    # ──────────────────────────────────────────────
    TRACKER_TYPE: str = "botsort.yaml"  # или "bytetrack.yaml"
    MAX_TRACK_AGE: int = 30  # Макс. кадров без детекции до удаления трека
    TRACK_BUFFER: int = 50

    # ──────────────────────────────────────────────
    # Настройки визуализации
    # ──────────────────────────────────────────────
    POSE_COLORS: Dict[str, Tuple[int, int, int]] = field(default_factory=lambda: {
        "standing": (0, 255, 0),      # Зелёный
        "sitting": (0, 165, 255),     # Оранжевый
        "hand_raised": (0, 0, 255),   # Красный
        "unknown": (128, 128, 128),   # Серый
    })

    SKELETON_COLOR: Tuple[int, int, int] = (255, 255, 0)
    KEYPOINT_COLOR: Tuple[int, int, int] = (0, 255, 255)
    BBOX_THICKNESS: int = 2
    TEXT_SCALE: float = 0.7
    TEXT_THICKNESS: int = 2
    KEYPOINT_RADIUS: int = 4

    # Соединения скелета (пары индексов ключевых точек)
    SKELETON_CONNECTIONS: list = field(default_factory=lambda: [
        (0, 1), (0, 2), (1, 3), (2, 4),        # Голова
        (5, 6),                                   # Плечи
        (5, 7), (7, 9),                           # Левая рука
        (6, 8), (8, 10),                          # Правая рука
        (5, 11), (6, 12),                         # Торс
        (11, 12),                                  # Бёдра
        (11, 13), (13, 15),                       # Левая нога
        (12, 14), (14, 16),                       # Правая нога
    ])

    # ──────────────────────────────────────────────
    # Настройки видео/камеры
    # ──────────────────────────────────────────────
    CAMERA_ID: int = 0
    VIDEO_WIDTH: int = 1280
    VIDEO_HEIGHT: int = 720
    VIDEO_FPS: int = 30

    # ──────────────────────────────────────────────
    # Настройки записи результатов
    # ──────────────────────────────────────────────
    SAVE_VIDEO: bool = False
    OUTPUT_VIDEO_PATH: str = "output_tracked.mp4"
    SAVE_LOGS: bool = True
    LOG_FILE: str = "pose_tracking_log.csv"


@dataclass
class TrainingConfig:
    """Конфигурация для обучения модели."""
    DATASET_PATH: str = "datasets/pose_dataset"
    EPOCHS: int = 100
    BATCH_SIZE: int = 16
    IMAGE_SIZE: int = 640
    LEARNING_RATE: float = 0.01
    PATIENCE: int = 20
    DEVICE: str = "auto"  # "cpu", "cuda", "mps", "auto"
    AUGMENT: bool = True
    PRETRAINED_MODEL: str = "yolov8n-pose.pt"
    PROJECT_NAME: str = "pose_training"
    EXPERIMENT_NAME: str = "exp1"