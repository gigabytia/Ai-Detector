from dataclasses import dataclass
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))  # backend/
DB_PATH = os.path.join(BASE_DIR, "analytics.db")

OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
SNAPSHOT_DIR = os.path.join(OUTPUT_DIR, "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

@dataclass
class Settings:
    MAX_CAMERAS: int = 8
    TARGET_FPS: float = 15.0

    # YOLO (обязательно pose-модель)
    MODEL_NAME: str = "yolov8s-pose.pt"
    IMGSZ: int = 960
    CONF: float = 0.25
    IOU: float = 0.45
    DEVICE: str = "auto"

    # Thresholds
    KP_POSE_THR: float = 0.30
    KP_DRAW_THR: float = 0.05

    HAND_KP_THR: float = 0.40

    # Hand raise (нормировано по bbox height) — сделаем строже вход/выход
    HAND_RAISE_ENTER_RATIO: float = 0.22
    HAND_RAISE_EXIT_RATIO: float = 0.16
    HAND_RAISE_CHAIN_RATIO: float = 0.08

    # Гистерезис по кадрам
    POSE_ENTER_FRAMES: int = 3
    HAND_RAISE_ENTER_FRAMES: int = 2
    HAND_RAISE_EXIT_FRAMES: int = 4

    # Walking thresholds
    WALK_SPEED_ABS_PX_PER_SEC: float = 25.0
    WALK_SPEED_REL_TO_BBOXH: float = 0.10

    # Events
    EVENT_COOLDOWN_SEC: float = 5.0
    LYING_ALERT_AFTER_SEC: float = 2.0

    TIMELINE_SAMPLE_SEC: float = 0.5

    STATE_DB_UPDATE_SEC: float = 0.5
    STATE_MISS_GAP_SEC: float = 1.0

SETTINGS = Settings()

SKELETON_EDGES = [
    (0, 1), (0, 2), (1, 3), (2, 4), (5, 6),
    (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]