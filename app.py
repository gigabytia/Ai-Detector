"""
Трекер поз с GPU-ускорением.
Улучшения:
- лучшая детекция дальних людей (imgsz выше, conf ниже, bytetrack)
- новые позы: standing, walking, lying (плюс сидит и рука поднята)
- быстрый рендер текста (см. text_renderer.py)
- адекватные сообщения без символов-эмодзи
"""
from ultralytics import YOLO
import cv2
import numpy as np
from collections import Counter, deque
import csv
import os
from datetime import datetime
import time
import torch
import subprocess
import sys

from text_renderer import put_russian_text, get_text_size, TEXT_BACKEND_NAME
from pose_analytics import AnalyticsCollector

WIN_NAME = "Pose Tracker [GPU]"

def get_screen_size():
    # кроссплатформенно и без доп. зависимостей (обычно работает на Windows/macOS/Linux)
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    return root.winfo_screenwidth(), root.winfo_screenheight()

def setup_window_fullscreen_if_needed(win_name: str, frame_w: int, frame_h: int):
    sw, sh = get_screen_size()

    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

    need_fullscreen = (frame_w > sw) or (frame_h > sh)
    if need_fullscreen:
        cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    else:
        cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_name, frame_w, frame_h)

    return need_fullscreen, sw, sh

def set_fullscreen(win_name: str, enable: bool, frame_w: int, frame_h: int):
    if enable:
        cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    else:
        cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_name, frame_w, frame_h)

# ============================================================
#  НАСТРОЙКИ
# ============================================================

VIDEO_SOURCE = "0415.mp4"

# Для дальних людей лучше начинать с yolov8s-pose.pt
# Если нужна скорость — оставьте yolov8n-pose.pt, но качество на дальних хуже
MODEL_NAME = "yolov8s-pose.pt"

# Детекция: для дальних людей обычно нужно 0.2-0.3
CONFIDENCE = 0.25
IOU = 0.45

SHOW_SKELETON = True

SAVE_LOGS = False
LOG_FILE = "pose_tracking_log.csv"

# Отчёт
GENERATE_REPORT = False
OPEN_REPORT = False
REPORTS_DIR = "reports"

# GPU
DEVICE = "auto"

# Ключевой параметр качества дальних людей:
# 320 почти всегда плохо для мелких людей
# 640 нормально, 960 заметно лучше, 1280 ещё лучше но медленнее
INFERENCE_SIZE = 960

USE_HALF_PRECISION = True

# Трекер
TRACKER_CFG = "bytetrack.yaml"
CLASSES = [0]     # person
MAX_DET = 50      # максимум детекций


# Пороги ключевых точек
KP_DRAW_THR = 0.20  # рисовать скелет можно мягче
KP_POSE_THR = 0.30  # позу определять чуть строже


# ============================================================
#  DEVICE
# ============================================================

def select_device(requested: str = "auto") -> str:
    print("=" * 60)
    print("Проверка устройства")
    print("=" * 60)

    if requested == "auto":
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            mem = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print("Режим: CUDA")
            print(f"GPU: {name}")
            print(f"VRAM: {mem:.1f} GB")
            print(f"CUDA (PyTorch): {torch.version.cuda}")
            return "cuda:0"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            print("Режим: Apple MPS")
            return "mps"
        else:
            print("Режим: CPU (CUDA недоступна)")
            return "cpu"

    if requested.startswith("cuda"):
        if torch.cuda.is_available():
            return requested
        print("Запрошена CUDA, но она недоступна. Используется CPU.")
        return "cpu"

    if requested == "mps":
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        print("Запрошен MPS, но он недоступен. Используется CPU.")
        return "cpu"

    return "cpu"


def print_gpu_info():
    if not torch.cuda.is_available():
        print("CUDA недоступна.")
        return
    print("\nGPU информация")
    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA: {torch.version.cuda}")
    print(f"cuDNN: {torch.backends.cudnn.version()}")
    for i in range(torch.cuda.device_count()):
        p = torch.cuda.get_device_properties(i)
        print(f"GPU #{i}: {p.name} | VRAM: {p.total_memory / 1024**3:.1f} GB | CC: {p.major}.{p.minor}")


# ============================================================
#  CSV LOGGER (буферизованный)
# ============================================================

class PoseCSVLogger:
    def __init__(self, log_file: str):
        self.log_file = log_file
        self._f = None
        self._writer = None
        self._buf = []
        self._flush_every = 200

    def _init_file(self):
        self._f = open(self.log_file, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._f)
        self._writer.writerow([
            "timestamp", "frame_number", "track_id",
            "pose", "pose_ru",
            "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2",
            "num_visible_kps", "total_people",
        ])

    def log_frame(self, frame_number, detections):
        if self._writer is None:
            self._init_file()

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        total = len(detections)

        pose_ru_map = {
            "standing": "Стоит",
            "walking": "Идёт",
            "sitting": "Сидит",
            "lying": "Лежит",
            "hand_raised": "Рука поднята",
            "unknown": "Неизвестно",
            "no_detection": "Нет людей",
        }

        if not detections:
            self._buf.append([ts, frame_number, -1, "no_detection", pose_ru_map["no_detection"], 0, 0, 0, 0, 0, 0])
        else:
            for det in detections:
                bbox = det["bbox"]
                confs = det.get("confidences", np.array([]))
                nv = int(np.sum(confs > KP_POSE_THR)) if len(confs) > 0 else 0
                self._buf.append([
                    ts, frame_number, det["track_id"],
                    det["pose"], pose_ru_map.get(det["pose"], det["pose"]),
                    f"{bbox[0]:.1f}", f"{bbox[1]:.1f}", f"{bbox[2]:.1f}", f"{bbox[3]:.1f}",
                    nv, total,
                ])

        if len(self._buf) >= self._flush_every:
            self.flush()

    def flush(self):
        if self._writer is None or not self._buf:
            return
        self._writer.writerows(self._buf)
        self._buf.clear()
        self._f.flush()

    def close(self):
        if self._writer is None:
            return
        self.flush()
        self._f.close()
        if os.path.exists(self.log_file):
            size = os.path.getsize(self.log_file) / 1024
            print(f"Лог сохранён: {self.log_file} ({size:.1f} KB)")


# ============================================================
#  ПОЗЫ
# ============================================================

def get_angle(a, b, c) -> float:
    ba = a - b
    bc = c - b
    dot = float(np.dot(ba, bc))
    mba = float(np.linalg.norm(ba))
    mbc = float(np.linalg.norm(bc))
    if mba == 0 or mbc == 0:
        return 180.0
    cosv = np.clip(dot / (mba * mbc), -1.0, 1.0)
    return float(np.degrees(np.arccos(cosv)))


def classify_pose_static(keypoints: np.ndarray, confidences: np.ndarray, bbox: np.ndarray) -> str:
    """
    Базовая поза без учёта движения (walking добавим отдельно по истории трека).
    Приоритет: hand_raised > lying > sitting > standing > unknown
    """
    thr = KP_POSE_THR

    # hand raised (оставляем вашу текущую логику, она у вас хорошо работает)
    if confidences[9] > thr and confidences[5] > thr:
        if keypoints[9][1] < keypoints[5][1] - 50:
            return "hand_raised"
    if confidences[10] > thr and confidences[6] > thr:
        if keypoints[10][1] < keypoints[6][1] - 50:
            return "hand_raised"
    if confidences[7] > thr and confidences[5] > thr and confidences[9] > thr:
        if keypoints[7][1] < keypoints[5][1] and keypoints[9][1] < keypoints[7][1]:
            return "hand_raised"
    if confidences[8] > thr and confidences[6] > thr and confidences[10] > thr:
        if keypoints[8][1] < keypoints[6][1] and keypoints[10][1] < keypoints[8][1]:
            return "hand_raised"

    # lying: широкий bbox и "плечи и бёдра" примерно на одном уровне по Y
    x1, y1, x2, y2 = bbox
    bw = max(1.0, x2 - x1)
    bh = max(1.0, y2 - y1)
    aspect = bw / bh

    if aspect > 1.35:
        # если видим плечи и бёдра — проверяем вертикальную разницу
        if all(confidences[i] > thr for i in [5, 6, 11, 12]):
            sh_y = (keypoints[5][1] + keypoints[6][1]) / 2.0
            hip_y = (keypoints[11][1] + keypoints[12][1]) / 2.0
            if abs(sh_y - hip_y) < 0.25 * bh:
                return "lying"
        else:
            # если ключевых точек мало, но bbox явно горизонтальный — тоже считаем лежит
            return "lying"

    # sitting
    sitting_score = 0
    if all(confidences[i] > thr for i in [11, 13, 15]):
        angle = get_angle(keypoints[11], keypoints[13], keypoints[15])
        if 50 < angle < 130:
            sitting_score += 1
    if all(confidences[i] > thr for i in [12, 14, 16]):
        angle = get_angle(keypoints[12], keypoints[14], keypoints[16])
        if 50 < angle < 130:
            sitting_score += 1

    if sitting_score >= 1:
        return "sitting"

    # standing
    if all(confidences[i] > thr for i in [11, 13, 15]):
        angle = get_angle(keypoints[11], keypoints[13], keypoints[15])
        if angle > 150:
            return "standing"
    if all(confidences[i] > thr for i in [12, 14, 16]):
        angle = get_angle(keypoints[12], keypoints[14], keypoints[16])
        if angle > 150:
            return "standing"

    if int(np.sum(confidences > thr)) >= 5:
        return "standing"

    return "unknown"


# ============================================================
#  WALKING по движению трека
# ============================================================

_motion_hist = {}  # track_id -> deque[(t_sec, cx, cy, bbox_h)]


def update_motion(track_id: int, t_sec: float, bbox: np.ndarray):
    x1, y1, x2, y2 = bbox
    cx = float((x1 + x2) / 2.0)
    cy = float((y1 + y2) / 2.0)
    bh = float(max(1.0, y2 - y1))

    dq = _motion_hist.get(track_id)
    if dq is None:
        dq = deque(maxlen=10)
        _motion_hist[track_id] = dq
    dq.append((t_sec, cx, cy, bh))


def is_walking(track_id: int) -> bool:
    dq = _motion_hist.get(track_id)
    if dq is None or len(dq) < 6:
        return False

    t0, cx0, cy0, bh0 = dq[0]
    t1, cx1, cy1, bh1 = dq[-1]
    dt = max(1e-3, float(t1 - t0))

    dist = float(np.hypot(cx1 - cx0, cy1 - cy0))  # px
    speed = dist / dt  # px/sec

    bh = max(1.0, float(np.median([x[3] for x in dq])))

    # Два условия: абсолютная скорость и относительная (к росту bbox)
    # Это снижает ложные walking из-за дрожания трека.
    return (speed > 25.0) and ((speed / bh) > 0.10)


# ============================================================
#  РИСОВАНИЕ
# ============================================================

POSE_COLORS = {
    "standing": (0, 255, 0),
    "walking": (255, 0, 0),
    "sitting": (0, 165, 255),
    "lying": (255, 0, 255),
    "hand_raised": (0, 0, 255),
    "unknown": (128, 128, 128),
}
POSE_NAMES_RU = {
    "standing": "Стоит",
    "walking": "Идёт",
    "sitting": "Сидит",
    "lying": "Лежит",
    "hand_raised": "Рука поднята",
    "unknown": "???",
}
SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4), (5, 6),
    (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]


def draw_skeleton(frame, keypoints, confidences):
    thr = KP_DRAW_THR
    for i, j in SKELETON:
        if confidences[i] > thr and confidences[j] > thr:
            pt1 = (int(keypoints[i][0]), int(keypoints[i][1]))
            pt2 = (int(keypoints[j][0]), int(keypoints[j][1]))
            cv2.line(frame, pt1, pt2, (255, 255, 0), 2)
    for idx in range(17):
        if confidences[idx] > thr:
            cv2.circle(frame, (int(keypoints[idx][0]), int(keypoints[idx][1])), 3, (0, 255, 255), -1)


def draw_bbox_and_label(frame, bbox, track_id, pose):
    x1, y1, x2, y2 = map(int, bbox)
    color = POSE_COLORS.get(pose, (128, 128, 128))
    label = f"ID:{track_id} {POSE_NAMES_RU.get(pose, pose)}"

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    font_size = 18
    tw, th = get_text_size(label, font_size)

    y_top = max(0, y1 - th - 12)
    x_right = min(frame.shape[1] - 1, x1 + tw + 10)
    cv2.rectangle(frame, (x1, y_top), (x_right, y1), color, -1)
    put_russian_text(frame, label, (x1 + 4, max(0, y1 - th - 8)), font_size, (255, 255, 255))


def draw_info_panel(frame, pose_counts, total, fps, device_name):
    cv2.rectangle(frame, (5, 5), (360, 250), (0, 0, 0), -1)
    cv2.rectangle(frame, (5, 5), (360, 250), (80, 80, 80), 1)

    font_size = 16
    y = 14

    dev_color = (0, 255, 0) if ("cuda" in device_name.lower() or "gpu" in device_name.lower()) else (0, 165, 255)
    put_russian_text(frame, f"Устройство: {device_name}", (12, y), font_size, dev_color)
    y += 28
    put_russian_text(frame, f"FPS: {fps:.0f}", (12, y), font_size, (0, 255, 0))
    y += 28
    put_russian_text(frame, f"Людей: {total}", (12, y), font_size, (255, 255, 255))
    y += 28

    order = ["standing", "walking", "sitting", "lying", "hand_raised"]
    for k in order:
        name = POSE_NAMES_RU[k]
        count = pose_counts.get(k, 0)
        put_russian_text(frame, f"{name}: {count}", (12, y), font_size, POSE_COLORS[k])
        y += 28


# ============================================================
#  СГЛАЖИВАНИЕ ПОЗ (лейбл)
# ============================================================

pose_history = {}


def smooth_pose(track_id, current_pose, history_len=5):
    if track_id not in pose_history:
        pose_history[track_id] = []
    pose_history[track_id].append(current_pose)
    if len(pose_history[track_id]) > history_len:
        pose_history[track_id].pop(0)
    return Counter(pose_history[track_id]).most_common(1)[0][0]


# ============================================================
#  MAIN
# ============================================================

def run_analysis(
    video_source,
    model_name,
    confidence,
    inference_size
):
    cv2.setUseOptimized(True)

    device = select_device(DEVICE)
    print_gpu_info()

    # Ultralytics: для CUDA надёжнее device=0, чем "cuda:0"
    if device.startswith("cuda"):
        ultra_device = 0
        device_display = f"GPU: {torch.cuda.get_device_name(0)}"
    elif device == "mps":
        ultra_device = "mps"
        device_display = "Apple MPS"
    else:
        ultra_device = "cpu"
        device_display = "CPU"

    # Torch оптимизации
    if device.startswith("cuda"):
        torch.backends.cudnn.benchmark = True
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True

    use_half = False
    if USE_HALF_PRECISION and device.startswith("cuda"):
        cap = torch.cuda.get_device_capability(0)
        use_half = cap[0] >= 7

    print("\nПараметры запуска")
    print(f"Источник: {video_source}")
    print(f"Модель: {MODEL_NAME}")
    print(f"Устройство: {device_display}")
    print(f"imgsz: {INFERENCE_SIZE}")
    print(f"conf: {CONFIDENCE}")
    print(f"half: {use_half}")
    print(f"Текст: {TEXT_BACKEND_NAME}")
    print("=" * 60)

    print("Загрузка модели...")
    model = YOLO(model_name)
    try:
        model.fuse()
    except Exception:
        pass

    # warmup
    if device.startswith("cuda"):
        dummy = np.zeros((INFERENCE_SIZE, INFERENCE_SIZE, 3), dtype=np.uint8)
        for _ in range(2):
            _ = model.predict(dummy, verbose=False, device=ultra_device, imgsz=INFERENCE_SIZE, half=use_half)
        torch.cuda.synchronize()

    logger = PoseCSVLogger(LOG_FILE) if SAVE_LOGS else None

    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        print("Ошибка: не удалось открыть видео.")
        return

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video_fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
    print(f"Видео: {w}x{h} @ {video_fps:.2f} FPS")
    is_fullscreen, screen_w, screen_h = setup_window_fullscreen_if_needed(WIN_NAME, w, h)

    analytics = AnalyticsCollector(
        source=str(VIDEO_SOURCE),
        fps=video_fps,
        frame_width=w,
        frame_height=h,
    )

    fps_times = []
    frame_count = 0
    paused = False
    exit_status = "interrupted"

    print("Управление: q - выход, s - скриншот, p - пауза")
    print("=" * 60)

    try:
        while True:
            if not paused:
                ret, frame = cap.read()
                if not ret:
                    exit_status = "completed"
                    print("Конец видео.")
                    break

                frame_count += 1
                t_now = time.time()

                fps_times.append(t_now)
                if len(fps_times) > 30:
                    fps_times.pop(0)
                fps = ((len(fps_times) - 1) / (fps_times[-1] - fps_times[0])) if len(fps_times) >= 2 else 0.0

                results = model.track(
                    frame,
                    persist=True,
                    conf=confidence,
                    iou=IOU,
                    classes=CLASSES,
                    max_det=MAX_DET,
                    tracker=TRACKER_CFG,
                    verbose=False,
                    device=ultra_device,
                    imgsz=inference_size,
                    half=use_half,
                )

                r = results[0]
                pose_counts = {}
                total_people = 0
                frame_detections = []

                if (r.boxes is not None and len(r.boxes) > 0 and r.keypoints is not None):
                    boxes = r.boxes.xyxy.cpu().numpy()
                    kp_data = r.keypoints.data.cpu().numpy()  # (N,17,3)

                    if r.boxes.id is not None:
                        track_ids = r.boxes.id.cpu().numpy().astype(int).tolist()
                    else:
                        track_ids = list(range(len(boxes)))

                    total_people = len(boxes)

                    for i in range(total_people):
                        bbox = boxes[i]
                        kps = kp_data[i, :, :2]
                        confs = kp_data[i, :, 2]
                        tid = int(track_ids[i])

                        # Обновляем историю движения (для walking)
                        t_sec = frame_count / video_fps
                        update_motion(tid, t_sec, bbox)

                        base_pose = classify_pose_static(kps, confs, bbox)

                        # walking: только если базово "standing"
                        pose = base_pose
                        if base_pose == "standing" and is_walking(tid):
                            pose = "walking"

                        # Сглаживание итоговой метки
                        pose = smooth_pose(tid, pose)

                        pose_counts[pose] = pose_counts.get(pose, 0) + 1

                        frame_detections.append({
                            "track_id": tid,
                            "bbox": bbox,
                            "pose": pose,
                            "confidences": confs,
                        })

                        if SHOW_SKELETON:
                            draw_skeleton(frame, kps, confs)
                        draw_bbox_and_label(frame, bbox, tid, pose)

                draw_info_panel(frame, pose_counts, total_people, fps, device_display)

                if logger:
                    logger.log_frame(frame_count, frame_detections)

                analytics.add_frame(frame_count, frame_detections)

                if frame_count % 30 == 0:
                    gpu_mem = ""
                    if device.startswith("cuda"):
                        mem = torch.cuda.memory_allocated(0) / 1024**2
                        gpu_mem = f", gpu_mem={mem:.0f}MB"
                    print(f"Кадр {frame_count}: people={total_people}, poses={pose_counts}, fps={fps:.1f}{gpu_mem}")

            cv2.imshow(WIN_NAME, frame)

            key = cv2.waitKey(1 if not paused else 100) & 0xFF
            if key == ord("q"):
                exit_status = "stopped_by_user"
                break
            elif key == ord("s"):
                fn = f"screenshot_{frame_count}.jpg"
                cv2.imwrite(fn, frame)
                print(f"Скриншот: {fn}")
            elif key == ord("p"):
                paused = not paused
            elif key == ord("f"):
                is_fullscreen = not is_fullscreen
                set_fullscreen(WIN_NAME, is_fullscreen, w, h)

    except KeyboardInterrupt:
        exit_status = "keyboard_interrupt"
        print("Остановлено с клавиатуры.")

    finally:
        cap.release()
        cv2.destroyAllWindows()

        if logger:
            logger.close()

        if device.startswith("cuda"):
            torch.cuda.empty_cache()

        print(f"Готово. Кадров обработано: {frame_count}")

        # --- Финализация и сохранение в БД ---
        summary = analytics.finalize(status=exit_status)

        from database import AnalyticsDB
        db = AnalyticsDB("analytics.db")
        run_id = db.save_summary(summary)

        print(f"Run сохранён в БД с id={run_id}")

def main():
    """
    При запуске app.py:
    1) Запускается Streamlit dashboard
    """

    print("Запуск Streamlit dashboard...")

    subprocess.run([
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "dashboard.py"
    ])


if __name__ == "__main__":
    main()