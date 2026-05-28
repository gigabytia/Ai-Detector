import os
from dataclasses import dataclass, field
from typing import List

_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
_env_path = os.path.abspath(_env_path)

if os.path.exists(_env_path):
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path)
        print(f"[config] Загружен .env: {_env_path}")
    except ImportError:
        #Если python-dotenv не установлен - читаем вручную
        print("[config] python-dotenv не установлен, читается .env вручную")
        with open(_env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                if key and key not in os.environ:
                    os.environ[key] = val
else:
    print(f"[config] .env не найден ({_env_path}), используются значения по умолчанию")

# ── Пути ──────────────────────────────────────────────────
BASE_DIR     = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH      = os.path.join(BASE_DIR, "analytics.db")
OUTPUT_DIR   = os.path.join(BASE_DIR, "outputs")
SNAPSHOT_DIR = os.path.join(OUTPUT_DIR, "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


# ── Хелперы ───────────────────────────────────────────────
def env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    try:
        return float(v) if v is not None else float(default)
    except (ValueError, TypeError):
        return float(default)


def env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    try:
        return int(v) if v is not None else int(default)
    except (ValueError, TypeError):
        return int(default)


def env_str(name: str, default: str) -> str:
    v = os.getenv(name)
    return str(v).strip() if v is not None else str(default)


def env_list(name: str, default: str) -> List[str]:
    #Читает строку вида 'box,pallet,forklift' → ['box', 'pallet', 'forklift']
    v = os.getenv(name, default)
    return [x.strip().lower() for x in v.split(",") if x.strip()]


#Настройки
@dataclass
class Settings:
    MAX_CAMERAS: int   = env_int("MAX_CAMERAS", 8)
    TARGET_FPS:  float = env_float("TARGET_FPS", 18.0)

    # модели
    MODEL_DET:  str = env_str("MODEL_DET",  "yolov8s.pt")
    MODEL_ROI:  str = env_str("MODEL_ROI",  "")
    MODEL_POSE: str = env_str("MODEL_POSE", "")

    # железо
    DEVICE:    str = env_str("DEVICE", "auto")
    IMGSZ_DET: int = env_int("IMGSZ_DET", 640)
    IMGSZ_ROI: int = env_int("IMGSZ_ROI", 640)

    # детекция
    CONF_DET: float = env_float("CONF_DET", 0.25)
    IOU_DET:  float = env_float("IOU_DET",  0.45)

    # классы (заполняются ниже через env_list)
    PERSON_CLASS_NAMES: List[str] = None
    OBJECT_CLASS_NAMES: List[str] = None

    # ROI
    ROI_ENABLED:             bool = env_int("ROI_ENABLED", 1) == 1
    ROI_MAX_CROPS_PER_TICK:  int  = env_int("ROI_MAX_CROPS_PER_TICK", 4)
    ROI_MIN_PERSON_H_PX:     int  = env_int("ROI_MIN_PERSON_H_PX", 120)
    ROI_ONLY_NEAR_EXIT_ZONE: bool = env_int("ROI_ONLY_NEAR_EXIT_ZONE", 1) == 1

    # логика carry-out
    CARRY_ASSOC_DIST_RATIO: float = env_float("CARRY_ASSOC_DIST_RATIO", 0.70)
    CARRY_MIN_HITS:         int   = env_int("CARRY_MIN_HITS", 4)

    EXIT_DWELL_SEC:     float = env_float("EXIT_DWELL_SEC",     0.25)
    EVENT_COOLDOWN_SEC: float = env_float("EVENT_COOLDOWN_SEC", 3.0)

    # таймлайн / БД
    TIMELINE_SAMPLE_SEC: float = env_float("TIMELINE_SAMPLE_SEC", 1.0)
    STATE_DB_UPDATE_SEC: float = env_float("STATE_DB_UPDATE_SEC", 1.0)
    STATE_MISS_GAP_SEC:  float = env_float("STATE_MISS_GAP_SEC",  1.2)

    # стримы
    RAW_STREAM_FPS:   float = env_float("RAW_STREAM_FPS",   6.0)
    ANNOT_STREAM_FPS: float = env_float("ANNOT_STREAM_FPS", 6.0)


SETTINGS = Settings()

# Классы читаем отдельно через env_list
if SETTINGS.PERSON_CLASS_NAMES is None:
    SETTINGS.PERSON_CLASS_NAMES = env_list("PERSON_CLASS_NAMES", "person")

if SETTINGS.OBJECT_CLASS_NAMES is None:
    SETTINGS.OBJECT_CLASS_NAMES = env_list("OBJECT_CLASS_NAMES", "box,pallet,forklift")

#Вывод итоговых настроек при импорте
print(f"[config] MODEL_DET  = {SETTINGS.MODEL_DET}")
print(f"[config] MODEL_ROI  = {SETTINGS.MODEL_ROI or '(не задан)'}")
print(f"[config] MODEL_POSE = {SETTINGS.MODEL_POSE or '(не задан)'}")
print(f"[config] DEVICE     = {SETTINGS.DEVICE}")
print(f"[config] PERSON_CLASS_NAMES = {SETTINGS.PERSON_CLASS_NAMES}")
print(f"[config] OBJECT_CLASS_NAMES = {SETTINGS.OBJECT_CLASS_NAMES}")