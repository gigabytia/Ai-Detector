import os
from dataclasses import dataclass
from typing import List

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))  # backend/
DB_PATH = os.path.join(BASE_DIR, "analytics.db")

OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
SNAPSHOT_DIR = os.path.join(OUTPUT_DIR, "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

def env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    return float(v) if v is not None else float(default)

def env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    return int(v) if v is not None else int(default)

def env_str(name: str, default: str) -> str:
    v = os.getenv(name)
    return str(v) if v is not None else str(default)

@dataclass
class Settings:
    MAX_CAMERAS: int = env_int("MAX_CAMERAS", 8)
    TARGET_FPS: float = env_float("TARGET_FPS", 18.0)

    # модели
    MODEL_DET: str = env_str("MODEL_DET", "yolov8s.pt")   # твоя обученная det-модель сюда
    MODEL_ROI: str = env_str("MODEL_ROI", "")            # опционально: отдельная модель для ROI, иначе будет MODEL_DET

    DEVICE: str = env_str("DEVICE", "auto")              # auto|cpu|cuda:0
    IMGSZ_DET: int = env_int("IMGSZ_DET", 736)
    IMGSZ_ROI: int = env_int("IMGSZ_ROI", 960)

    CONF_DET: float = env_float("CONF_DET", 0.25)
    IOU_DET: float = env_float("IOU_DET", 0.45)

    # классы (имена должны совпадать с model.names)
    PERSON_CLASS_NAMES: List[str] = None
    OBJECT_CLASS_NAMES: List[str] = None

    # ROI stage
    ROI_ENABLED: bool = env_int("ROI_ENABLED", 1) == 1
    ROI_MAX_CROPS_PER_TICK: int = env_int("ROI_MAX_CROPS_PER_TICK", 4)
    ROI_MIN_PERSON_H_PX: int = env_int("ROI_MIN_PERSON_H_PX", 120)  # если человек слишком маленький - ROI может помочь
    ROI_ONLY_NEAR_EXIT_ZONE: bool = env_int("ROI_ONLY_NEAR_EXIT_ZONE", 1) == 1

    # association person-object ("несёт")
    CARRY_ASSOC_DIST_RATIO: float = env_float("CARRY_ASSOC_DIST_RATIO", 0.70)  # dist < ratio*bbox_h
    CARRY_MIN_HITS: int = env_int("CARRY_MIN_HITS", 4)  # кадров подтверждения

    # exit zone logic
    EXIT_DWELL_SEC: float = env_float("EXIT_DWELL_SEC", 0.25)

    # события
    EVENT_COOLDOWN_SEC: float = env_float("EVENT_COOLDOWN_SEC", 3.0)

    # БД
    TIMELINE_SAMPLE_SEC: float = env_float("TIMELINE_SAMPLE_SEC", 1.0)
    STATE_DB_UPDATE_SEC: float = env_float("STATE_DB_UPDATE_SEC", 1.0)
    STATE_MISS_GAP_SEC: float = env_float("STATE_MISS_GAP_SEC", 1.2)

SETTINGS = Settings()
if SETTINGS.PERSON_CLASS_NAMES is None:
    SETTINGS.PERSON_CLASS_NAMES = ["person"]
if SETTINGS.OBJECT_CLASS_NAMES is None:
    SETTINGS.OBJECT_CLASS_NAMES = ["box", "pallet", "tool"]

SETTINGS.PERSON_CLASS_NAMES = [x.strip().lower() for x in SETTINGS.PERSON_CLASS_NAMES]
SETTINGS.OBJECT_CLASS_NAMES = [x.strip().lower() for x in SETTINGS.OBJECT_CLASS_NAMES]