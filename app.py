"""
Трекер поз с GPU-ускорением.
Рендеринг модели на видеокарте NVIDIA (CUDA).
"""
from ultralytics import YOLO
import cv2
import numpy as np
from collections import Counter
import csv
import os
from datetime import datetime
import time
import torch

from text_renderer import put_russian_text, get_text_size


# ============================================================
#  НАСТРОЙКИ
# ============================================================

VIDEO_SOURCE = "video.mp4"
MODEL_NAME = "yolov8n-pose.pt"
CONFIDENCE = 0.5
SHOW_SKELETON = True
SAVE_LOGS = True
LOG_FILE = "pose_tracking_log.csv"

# ── GPU НАСТРОЙКИ ──
# "auto" = автоматически (GPU если есть, иначе CPU)
# "cuda" или "cuda:0" = первая видеокарта
# "cuda:1" = вторая видеокарта
# "cpu" = принудительно CPU
DEVICE = "auto"

# Размер входного изображения для модели
# Меньше = быстрее, но менее точно
# 640 — стандарт, 320 — быстро, 1280 — точно
INFERENCE_SIZE = 640

# FP16 (half precision) — ускоряет на GPU в 1.5-2 раза
# Работает только на GPU с Tensor Cores (RTX 20xx+)
USE_HALF_PRECISION = True


# ============================================================
#  ОПРЕДЕЛЕНИЕ УСТРОЙСТВА
# ============================================================

def select_device(requested: str = "auto") -> str:
    """
    Определяет лучшее доступное устройство.

    Returns:
        "cuda:0", "mps" или "cpu"
    """
    print("=" * 50)
    print("  Проверка GPU...")
    print("=" * 50)

    if requested == "auto":
        # NVIDIA GPU (CUDA)
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(f"  ✅ NVIDIA GPU найдена: {gpu_name}")
            print(f"     Видеопамять: {gpu_mem:.1f} GB")
            print(f"     CUDA версия: {torch.version.cuda}")
            return "cuda:0"

        # Apple Silicon (MPS)
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            print(f"  ✅ Apple Silicon (MPS) найден")
            return "mps"

        # Только CPU
        else:
            print(f"  ⚠️  GPU не найдена, используется CPU")
            print(f"     Совет: установи CUDA-версию PyTorch")
            return "cpu"

    elif requested.startswith("cuda"):
        if torch.cuda.is_available():
            device_id = int(requested.split(":")[-1]) if ":" in requested else 0
            gpu_name = torch.cuda.get_device_name(device_id)
            print(f"  ✅ Используется GPU: {gpu_name}")
            return requested
        else:
            print(f"  ❌ CUDA недоступна! Падаем на CPU")
            return "cpu"

    elif requested == "mps":
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return "mps"
        else:
            print(f"  ❌ MPS недоступен! Падаем на CPU")
            return "cpu"

    else:
        return "cpu"


def print_gpu_info():
    """Выводит подробную информацию о GPU."""
    if not torch.cuda.is_available():
        print("  GPU (CUDA) не доступна")
        return

    print(f"\n  === GPU Info ===")
    print(f"  PyTorch: {torch.__version__}")
    print(f"  CUDA: {torch.version.cuda}")
    print(f"  cuDNN: {torch.backends.cudnn.version()}")

    for i in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(i)
        print(f"\n  GPU #{i}: {props.name}")
        print(f"    Видеопамять: {props.total_memory / 1024**3:.1f} GB")
        print(f"    Compute Capability: {props.major}.{props.minor}")
        print(f"    SM процессоры: {props.multi_processor_count}")

    # Текущее использование памяти
    allocated = torch.cuda.memory_allocated(0) / 1024**2
    cached = torch.cuda.memory_reserved(0) / 1024**2
    print(f"\n  Память GPU:")
    print(f"    Занято: {allocated:.0f} MB")
    print(f"    Кеш: {cached:.0f} MB")


# ============================================================
#  ЛОГИРОВАНИЕ В CSV
# ============================================================

class PoseCSVLogger:
    """Записывает результаты трекинга в CSV."""

    def __init__(self, log_file: str = "pose_tracking_log.csv"):
        self.log_file = log_file
        self._initialized = False

    def _init_file(self):
        with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'frame_number', 'track_id',
                'pose', 'pose_ru',
                'bbox_x1', 'bbox_y1', 'bbox_x2', 'bbox_y2',
                'num_visible_kps', 'total_people',
            ])
        self._initialized = True

    def log_frame(self, frame_number, detections):
        if not self._initialized:
            self._init_file()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        total = len(detections)

        pose_ru_map = {
            "standing": "Стоит", "sitting": "Сидит",
            "hand_raised": "Рука поднята", "unknown": "Неизвестно",
        }

        with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not detections:
                writer.writerow([
                    timestamp, frame_number, -1,
                    'no_detection', 'Нет людей',
                    0, 0, 0, 0, 0, 0,
                ])
            else:
                for det in detections:
                    bbox = det["bbox"]
                    confs = det.get("confidences", np.array([]))
                    nv = int(np.sum(confs > 0.3)) if len(confs) > 0 else 0
                    writer.writerow([
                        timestamp, frame_number, det["track_id"],
                        det["pose"], pose_ru_map.get(det["pose"], "?"),
                        f"{bbox[0]:.1f}", f"{bbox[1]:.1f}",
                        f"{bbox[2]:.1f}", f"{bbox[3]:.1f}",
                        nv, total,
                    ])

    def close(self):
        if self._initialized:
            size = os.path.getsize(self.log_file) / 1024
            print(f"  [LOG] Сохранён: {self.log_file} ({size:.1f} КБ)")


# ============================================================
#  ОПРЕДЕЛЕНИЕ ПОЗЫ
# ============================================================

def get_angle(point_a, point_b, point_c):
    ba = point_a - point_b
    bc = point_c - point_b
    dot = np.dot(ba, bc)
    mag_ba = np.linalg.norm(ba)
    mag_bc = np.linalg.norm(bc)
    if mag_ba == 0 or mag_bc == 0:
        return 180.0
    cos_angle = np.clip(dot / (mag_ba * mag_bc), -1.0, 1.0)
    return np.degrees(np.arccos(cos_angle))


def classify_pose(keypoints, confidences):
    MIN_CONF = 0.3
    hand_raised = False

    if confidences[9] > MIN_CONF and confidences[5] > MIN_CONF:
        if keypoints[9][1] < keypoints[5][1] - 50:
            hand_raised = True
    if confidences[10] > MIN_CONF and confidences[6] > MIN_CONF:
        if keypoints[10][1] < keypoints[6][1] - 50:
            hand_raised = True
    if confidences[7] > MIN_CONF and confidences[5] > MIN_CONF and confidences[9] > MIN_CONF:
        if keypoints[7][1] < keypoints[5][1] and keypoints[9][1] < keypoints[7][1]:
            hand_raised = True
    if confidences[8] > MIN_CONF and confidences[6] > MIN_CONF and confidences[10] > MIN_CONF:
        if keypoints[8][1] < keypoints[6][1] and keypoints[10][1] < keypoints[8][1]:
            hand_raised = True
    if hand_raised:
        return "hand_raised"

    sitting_score = 0
    if all(confidences[i] > MIN_CONF for i in [11, 13, 15]):
        angle = get_angle(keypoints[11], keypoints[13], keypoints[15])
        if 50 < angle < 130:
            sitting_score += 1
    if all(confidences[i] > MIN_CONF for i in [12, 14, 16]):
        angle = get_angle(keypoints[12], keypoints[14], keypoints[16])
        if 50 < angle < 130:
            sitting_score += 1
    if all(confidences[i] > MIN_CONF for i in [5, 6, 11, 12, 13, 14]):
        mid_hip_y = (keypoints[11][1] + keypoints[12][1]) / 2
        mid_knee_y = (keypoints[13][1] + keypoints[14][1]) / 2
        mid_shoulder_y = (keypoints[5][1] + keypoints[6][1]) / 2
        torso = abs(mid_hip_y - mid_shoulder_y)
        if torso > 0:
            ratio = abs(mid_hip_y - mid_knee_y) / torso
            if ratio < 0.3:
                sitting_score += 1
    if sitting_score >= 1:
        return "sitting"

    if all(confidences[i] > MIN_CONF for i in [11, 13, 15]):
        angle = get_angle(keypoints[11], keypoints[13], keypoints[15])
        if angle > 150:
            return "standing"
    if all(confidences[i] > MIN_CONF for i in [12, 14, 16]):
        angle = get_angle(keypoints[12], keypoints[14], keypoints[16])
        if angle > 150:
            return "standing"
    if all(confidences[i] > MIN_CONF for i in [11, 13, 15]):
        if keypoints[11][1] < keypoints[13][1] - 30:
            if keypoints[13][1] < keypoints[15][1] - 30:
                return "standing"

    if np.sum(confidences > MIN_CONF) >= 5:
        return "standing"

    return "unknown"


# ============================================================
#  РИСОВАНИЕ
# ============================================================

POSE_COLORS = {
    "standing": (0, 255, 0), "sitting": (0, 165, 255),
    "hand_raised": (0, 0, 255), "unknown": (128, 128, 128),
}
POSE_NAMES_RU = {
    "standing": "Стоит", "sitting": "Сидит",
    "hand_raised": "Рука поднята", "unknown": "???",
}
SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4), (5, 6),
    (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]


def draw_skeleton(frame, keypoints, confidences):
    for i, j in SKELETON:
        if confidences[i] > 0.3 and confidences[j] > 0.3:
            pt1 = (int(keypoints[i][0]), int(keypoints[i][1]))
            pt2 = (int(keypoints[j][0]), int(keypoints[j][1]))
            cv2.line(frame, pt1, pt2, (255, 255, 0), 2)
    for idx in range(17):
        if confidences[idx] > 0.3:
            cv2.circle(frame, (int(keypoints[idx][0]), int(keypoints[idx][1])), 4, (0, 255, 255), -1)


def draw_bbox_and_label(frame, bbox, track_id, pose):
    x1, y1, x2, y2 = map(int, bbox)
    color = POSE_COLORS.get(pose, (128, 128, 128))
    label = f"ID:{track_id} {POSE_NAMES_RU.get(pose, pose)}"
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    font_size = 18
    tw, th = get_text_size(label, font_size)
    cv2.rectangle(frame, (x1, y1 - th - 12), (x1 + tw + 10, y1), color, -1)
    put_russian_text(frame, label, (x1 + 4, y1 - th - 8), font_size, (255, 255, 255))


def draw_info_panel(frame, pose_counts, total, fps, device_name):
    """Панель информации с устройством."""
    cv2.rectangle(frame, (5, 5), (320, 210), (0, 0, 0), -1)
    cv2.rectangle(frame, (5, 5), (320, 210), (80, 80, 80), 1)

    font_size = 16
    y = 14

    # Устройство (GPU/CPU)
    dev_color = (0, 255, 0) if "cuda" in device_name.lower() or "gpu" in device_name.lower() else (0, 165, 255)
    put_russian_text(frame, f"Устройство: {device_name}", (12, y), font_size, dev_color)
    y += 28

    put_russian_text(frame, f"FPS: {fps:.0f}", (12, y), font_size, (0, 255, 0))
    y += 28

    put_russian_text(frame, f"Людей: {total}", (12, y), font_size, (255, 255, 255))
    y += 28

    for pose_key, pose_name in POSE_NAMES_RU.items():
        if pose_key == "unknown":
            continue
        count = pose_counts.get(pose_key, 0)
        color = POSE_COLORS[pose_key]
        put_russian_text(frame, f"{pose_name}: {count}", (12, y), font_size, color)
        y += 28


# ============================================================
#  СГЛАЖИВАНИЕ
# ============================================================

pose_history = {}


def smooth_pose(track_id, current_pose, history_len=5):
    if track_id not in pose_history:
        pose_history[track_id] = []
    pose_history[track_id].append(current_pose)
    if len(pose_history[track_id]) > history_len:
        pose_history[track_id].pop(0)
    counter = Counter(pose_history[track_id])
    return counter.most_common(1)[0][0]


# ============================================================
#  ГЛАВНЫЙ ЦИКЛ
# ============================================================

def main():
    # ── Выбор устройства ──
    device = select_device(DEVICE)
    print_gpu_info()

    # ── Загрузка модели НА GPU ──
    print(f"\n  Загрузка модели {MODEL_NAME} на {device}...")
    model = YOLO(MODEL_NAME)

    # Перенос модели на GPU
    model.to(device)

    # Определяем название устройства для отображения
    if device.startswith("cuda"):
        device_display = f"GPU: {torch.cuda.get_device_name(0)}"
    elif device == "mps":
        device_display = "Apple GPU (MPS)"
    else:
        device_display = "CPU"

    print(f"  ✅ Модель загружена на: {device_display}")

    # ── Проверка FP16 ──
    use_half = False
    if USE_HALF_PRECISION and device.startswith("cuda"):
        # Проверяем поддержку FP16
        capability = torch.cuda.get_device_capability(0)
        if capability[0] >= 7:  # Volta+ (RTX 20xx, 30xx, 40xx)
            use_half = True
            print(f"  ✅ FP16 (half precision) включён — ускорение ~1.5x")
        else:
            print(f"  ⚠️  FP16 не поддерживается на вашей GPU")
    elif USE_HALF_PRECISION:
        print(f"  ⚠️  FP16 работает только на NVIDIA GPU")

    print()
    print("  Управление: q=выход, s=скриншот, p=пауза")
    print("=" * 50)

    # ── Прогрев GPU (warmup) ──
    if device.startswith("cuda"):
        print("  Прогрев GPU...")
        dummy = np.zeros((INFERENCE_SIZE, INFERENCE_SIZE, 3), dtype=np.uint8)
        for _ in range(3):
            model.predict(dummy, verbose=False, device=device)
        torch.cuda.synchronize()
        print("  GPU прогрета!")

    # ── Логгер ──
    logger = PoseCSVLogger(LOG_FILE) if SAVE_LOGS else None

    # ── Видео ──
    cap = cv2.VideoCapture(VIDEO_SOURCE)
    if not cap.isOpened():
        print("\nОШИБКА: Не удалось открыть видео!")
        return

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video_fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30
    print(f"  Видео: {w}x{h} @ {video_fps} FPS")

    fps_times = []
    frame_count = 0
    paused = False

    try:
        while True:
            if not paused:
                ret, frame = cap.read()
                if not ret:
                    print("Конец видео")
                    break

                frame_count += 1

                # FPS
                fps_times.append(time.time())
                if len(fps_times) > 30:
                    fps_times.pop(0)
                fps = ((len(fps_times) - 1) / (fps_times[-1] - fps_times[0])
                       if len(fps_times) >= 2 else 0)

                # ══════════════════════════════════════════
                #  ИНФЕРЕНС НА GPU
                # ══════════════════════════════════════════
                results = model.track(
                    frame,
                    persist=True,
                    conf=CONFIDENCE,
                    verbose=False,
                    device=device,         # ← GPU!
                    imgsz=INFERENCE_SIZE,   # ← Размер входа
                    half=use_half,          # ← FP16 ускорение
                )
                # ══════════════════════════════════════════

                result = results[0]
                pose_counts = {}
                total_people = 0
                frame_detections = []

                if (result.boxes is not None
                        and len(result.boxes) > 0
                        and result.keypoints is not None):

                    boxes = result.boxes.xyxy.cpu().numpy()
                    kp_data = result.keypoints.data.cpu().numpy()

                    if result.boxes.id is not None:
                        track_ids = result.boxes.id.cpu().numpy().astype(int).tolist()
                    else:
                        track_ids = list(range(len(boxes)))

                    total_people = len(boxes)

                    for i in range(len(boxes)):
                        bbox = boxes[i]
                        kps = kp_data[i, :, :2]
                        confs = kp_data[i, :, 2]
                        tid = track_ids[i]

                        pose = classify_pose(kps, confs)
                        pose = smooth_pose(tid, pose)
                        pose_counts[pose] = pose_counts.get(pose, 0) + 1

                        frame_detections.append({
                            "track_id": tid, "bbox": bbox,
                            "pose": pose, "confidences": confs,
                        })

                        if SHOW_SKELETON:
                            draw_skeleton(frame, kps, confs)
                        draw_bbox_and_label(frame, bbox, tid, pose)

                draw_info_panel(frame, pose_counts, total_people, fps, device_display)

                if logger:
                    logger.log_frame(frame_count, frame_detections)

                if frame_count % 30 == 0:
                    # GPU память
                    gpu_mem = ""
                    if device.startswith("cuda"):
                        mem = torch.cuda.memory_allocated(0) / 1024**2
                        gpu_mem = f", GPU mem: {mem:.0f}MB"
                    print(f"  Кадр {frame_count}: людей={total_people}, "
                          f"позы={pose_counts}, FPS={fps:.1f}{gpu_mem}")

            cv2.imshow("Pose Tracker [GPU]", frame)

            key = cv2.waitKey(1 if not paused else 100) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                fn = f"screenshot_{frame_count}.jpg"
                cv2.imwrite(fn, frame)
                print(f"  Скриншот: {fn}")
            elif key == ord('p'):
                paused = not paused

    finally:
        cap.release()
        cv2.destroyAllWindows()
        if logger:
            logger.close()

        # Очистка GPU памяти
        if device.startswith("cuda"):
            torch.cuda.empty_cache()
            print("  GPU память очищена")

        print(f"\nГотово! Кадров: {frame_count}")


if __name__ == "__main__":
    main()