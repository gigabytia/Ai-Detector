import os
import time
import threading
import queue
import traceback
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

import cv2
import numpy as np

from .config import SETTINGS
from .storage.store import AnalyticsStore
from .pipeline.detector import YOLODetector
from .pipeline.roi import ROIPipeline
from .pipeline.geometry import point_in_poly, line_side, has_crossed
from .pipeline.events import EventEmitter
from .pipeline.visualize import draw_overlay_bgr
from .pipeline.trackers import ByteTracker

cv2.setNumThreads(0)


def _compute_carry_score(
    person_xyxy: Tuple[float, float, float, float],
    obj_xyxy: Tuple[float, float, float, float],
    obj_cls: str,
    keypoints_px: Optional[List[List[float]]] = None,
) -> float:
    px1, py1, px2, py2 = person_xyxy
    ox1, oy1, ox2, oy2 = obj_xyxy

    ph = max(1.0, py2 - py1)
    pw = max(1.0, px2 - px1)
    oh = max(1.0, oy2 - oy1)
    ow = max(1.0, ox2 - ox1)

    pcx = (px1 + px2) / 2.0
    pcy = (py1 + py2) / 2.0
    ocx = (ox1 + ox2) / 2.0
    ocy = (oy1 + oy2) / 2.0

    score = 0.0

    # 1. Расстояние (0..0.35)
    dist = ((pcx - ocx) ** 2 + (pcy - ocy) ** 2) ** 0.5
    dist_ratio = dist / ph
    if dist_ratio < 0.3:
        score += 0.35
    elif dist_ratio < 0.5:
        score += 0.25
    elif dist_ratio < 0.7:
        score += 0.10

    # 2. Перекрытие bbox (0..0.25)
    inter_x1 = max(px1, ox1)
    inter_y1 = max(py1, oy1)
    inter_x2 = min(px2, ox2)
    inter_y2 = min(py2, oy2)
    inter_area = max(0.0, inter_x2 - inter_x1) * max(0.0, inter_y2 - inter_y1)
    obj_area = ow * oh
    overlap = inter_area / obj_area if obj_area > 0 else 0.0
    if overlap > 0.5:
        score += 0.25
    elif overlap > 0.2:
        score += 0.15
    elif overlap > 0.05:
        score += 0.05

    # 3. Вертикальная позиция (0..0.15)
    obj_rel_y = (ocy - py1) / ph
    if 0.3 <= obj_rel_y <= 0.85:
        score += 0.15
    elif 0.15 <= obj_rel_y <= 0.95:
        score += 0.08

    # 4. Размер объекта (0..0.10)
    size_ratio = (oh * ow) / (ph * pw) if (ph * pw) > 0 else 0
    if 0.02 < size_ratio < 0.6:
        score += 0.10
    elif 0.005 < size_ratio < 0.8:
        score += 0.05

    # 5. Pose wrists (0..0.15)
    if keypoints_px is not None and len(keypoints_px) >= 11:
        lw = keypoints_px[9]
        rw = keypoints_px[10]
        wrist_score = 0.0
        for wrist in [lw, rw]:
            wx, wy, wc = wrist
            if wc < 0.3:
                continue
            wdist = ((wx - ocx) ** 2 + (wy - ocy) ** 2) ** 0.5
            if wdist < 0.3 * ph:
                wrist_score += 0.10
            elif wdist < 0.5 * ph:
                wrist_score += 0.05
        score += min(0.15, wrist_score)

    return min(1.0, score)


@dataclass
class InferenceItem:
    camera_id: int
    frame_bgr: np.ndarray
    t_sec: float
    t_wall: float


@dataclass
class CameraRuntime:
    camera_id: int
    name: str
    path: str
    status: str = "running"

    frame_w: int = 0
    frame_h: int = 0
    fps_src: float = 30.0
    duration_sec: float = 0.0

    last_overlay: Dict[str, Any] = field(
        default_factory=lambda: {"ts": 0.0, "t_sec": 0.0, "detections": [], "config": {}}
    )
    last_jpeg: Optional[bytes] = None
    last_annotated_jpeg: Optional[bytes] = None
    last_jpeg_ts: float = 0.0
    last_annotated_jpeg_ts: float = 0.0
    last_timeline_sec: float = -1.0

    _q: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=1))
    _stop: threading.Event = field(default_factory=threading.Event)
    _jpeg_lock: threading.Lock = field(default_factory=threading.Lock)

    _cfg_cache: Dict[str, Any] = field(default_factory=dict)
    _cfg_cache_ts: float = 0.0

    person_tracker: ByteTracker = field(
        default_factory=lambda: ByteTracker(
            track_thresh=SETTINGS.CONF_DET,
            match_iou_thr=0.35,
            max_age=30,
            min_hits=2,
            grace=3,
        )
    )
    obj_tracker: ByteTracker = field(
        default_factory=lambda: ByteTracker(
            track_thresh=SETTINGS.CONF_OBJ,
            match_iou_thr=0.35,
            max_age=40,
            min_hits=2,
            grace=4,
        )
    )

    person_mem: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    emitter: EventEmitter = field(default_factory=EventEmitter)


_CFG_CACHE_TTL = 2.0
CARRY_SCORE_THRESHOLD = 0.40
LOITER_THRESHOLD_SEC = 10.0


class TrackStateRecorder:
    def __init__(self, store: AnalyticsStore):
        self.store = store
        self._lock = threading.Lock()
        self.active: Dict[Tuple[int, int], Dict[str, Any]] = {}

    def update(self, camera_id: int, people: List[Dict[str, Any]], t_sec: float):
        now = float(t_sec)
        seen: set = set()
        with self._lock:
            for p in people:
                tid = int(p["track_id"])
                state = str(p.get("state", "normal"))
                key = (int(camera_id), tid)
                seen.add(key)
                cur = self.active.get(key)
                if cur is None:
                    seg_id = self.store.start_segment(camera_id, tid, state, now)
                    self.active[key] = {"seg_id": seg_id, "state": state, "last_seen": now, "last_db": now}
                    continue
                cur["last_seen"] = now
                if state != cur["state"]:
                    self.store.update_segment_end(cur["seg_id"], now)
                    seg_id = self.store.start_segment(camera_id, tid, state, now)
                    cur.update({"seg_id": seg_id, "state": state, "last_db": now})
                else:
                    if (now - cur["last_db"]) >= SETTINGS.STATE_DB_UPDATE_SEC:
                        self.store.update_segment_end(cur["seg_id"], now)
                        cur["last_db"] = now
            to_close = [
                (key, cur) for key, cur in self.active.items()
                if key not in seen and (now - cur["last_seen"]) >= SETTINGS.STATE_MISS_GAP_SEC
            ]
            for key, cur in to_close:
                self.store.update_segment_end(cur["seg_id"], cur["last_seen"])
                self.active.pop(key, None)


class CameraManager:
    def __init__(self, upload_dir: str):
        self.upload_dir = upload_dir
        os.makedirs(upload_dir, exist_ok=True)

        self._lock = threading.Lock()
        self.cameras: Dict[int, CameraRuntime] = {}
        self._next_id = 1

        self.store = AnalyticsStore()
        self.state_rec = TrackStateRecorder(self.store)

        # Модель для людей (COCO)
        self.det = YOLODetector(
            model_path=SETTINGS.MODEL_DET,
            device=SETTINGS.DEVICE,
            imgsz=SETTINGS.IMGSZ_DET,
            conf=SETTINGS.CONF_DET,
            iou=SETTINGS.IOU_DET,
        )

        # Модель для объектов (обученная)
        self.obj_det = None
        if SETTINGS.MODEL_ROI.strip():
            try:
                self.obj_det = YOLODetector(
                    model_path=SETTINGS.MODEL_ROI.strip(),
                    device=SETTINGS.DEVICE,
                    imgsz=SETTINGS.IMGSZ_ROI,
                    conf=SETTINGS.CONF_OBJ,
                    iou=SETTINGS.IOU_DET,
                )
                print(f"OBJ model loaded: {SETTINGS.MODEL_ROI}")
            except Exception as e:
                print(f"OBJ model FAILED: {e}")
                self.obj_det = None
        else:
            print("OBJ model: disabled (MODEL_ROI not set)")

        # ── Pose модель ──────────────────────────────────
        self.pose_model = None
        pose_path = getattr(SETTINGS, "MODEL_POSE", "")
        if pose_path:
            try:
                from ultralytics import YOLO
                self.pose_model = YOLO(pose_path)
                print(f"POSE model loaded: {pose_path}")
            except Exception as e:
                print(f"POSE model FAILED: {e}")
        else:
            print("POSE model: disabled")

        # ROIPipeline (для совместимости, не используется напрямую)
        self.roi = ROIPipeline(det=self.det, roi_det=None)

        self._stop_all = threading.Event()
        self._infer_thread = threading.Thread(target=self._infer_loop, daemon=True, name="infer-loop")
        self._infer_thread.start()

        self._subs_lock = threading.Lock()
        self._event_subs: List[queue.Queue] = []

        print("=" * 50)
        print(f"MODEL_DET  = {SETTINGS.MODEL_DET} (person)")
        print(f"MODEL_ROI  = {SETTINGS.MODEL_ROI or 'NONE'} (objects)")
        print(f"MODEL_POSE = {pose_path or 'NONE'} (skeleton)")
        print(f"PERSON_CLASS_NAMES = {SETTINGS.PERSON_CLASS_NAMES}")
        print(f"OBJECT_CLASS_NAMES = {SETTINGS.OBJECT_CLASS_NAMES}")
        print(f"CONF_DET = {SETTINGS.CONF_DET}")
        print("=" * 50)

    #helpers
    def get_status(self, camera_id: int) -> Optional[str]:
        with self._lock:
            rt = self.cameras.get(camera_id)
            return rt.status if rt else None

    def get_jpeg_packet(self, camera_id: int) -> Tuple[float, Optional[bytes]]:
        with self._lock:
            rt = self.cameras.get(camera_id)
            if not rt:
                return 0.0, None
        with rt._jpeg_lock:
            return float(rt.last_jpeg_ts), rt.last_jpeg

    def get_annotated_jpeg_packet(self, camera_id: int) -> Tuple[float, Optional[bytes]]:
        with self._lock:
            rt = self.cameras.get(camera_id)
            if not rt:
                return 0.0, None
        with rt._jpeg_lock:
            return float(rt.last_annotated_jpeg_ts), rt.last_annotated_jpeg

    def shutdown(self):
        self._stop_all.set()
        with self._lock:
            for rt in self.cameras.values():
                rt._stop.set()
                rt.status = "stopped"

    def subscribe_events(self) -> queue.Queue:
        q = queue.Queue(maxsize=200)
        with self._subs_lock:
            self._event_subs.append(q)
        return q

    def unsubscribe_events(self, q: queue.Queue):
        with self._subs_lock:
            self._event_subs = [x for x in self._event_subs if x is not q]

    def _publish_event(self, ev: Dict[str, Any]):
        with self._subs_lock:
            subs = list(self._event_subs)
        dead = []
        for q in subs:
            try:
                q.put_nowait(ev)
            except Exception:
                dead.append(q)
        for q in dead:
            self.unsubscribe_events(q)

    def add_videos(self, files: List[Tuple[str, str]]) -> List[int]:
        with self._lock:
            if len(self.cameras) + len(files) > SETTINGS.MAX_CAMERAS:
                raise ValueError(f"Максимум {SETTINGS.MAX_CAMERAS} камер")
        ids = []
        for orig_name, path in files:
            camera_id = self._alloc_id()
            safe_name = f"cam{camera_id}_{os.path.basename(orig_name)}"
            rt = CameraRuntime(camera_id=camera_id, name=safe_name, path=path)
            self._init_capture_meta(rt)
            self._reset_camera_data(camera_id)
            with self._lock:
                self.cameras[camera_id] = rt
            t = threading.Thread(target=self._reader_loop, args=(rt,), daemon=True, name=f"reader-{camera_id}")
            t.start()
            ids.append(camera_id)
        return ids

    def _reset_camera_data(self, camera_id: int):
        try:
            self.store.set_camera_config(camera_id, exit_line=None, exit_zone=None)
            self.store.clear_camera(camera_id)
        except Exception:
            traceback.print_exc()

    def _alloc_id(self) -> int:
        with self._lock:
            cid = self._next_id
            self._next_id += 1
        return cid

    def _init_capture_meta(self, rt: CameraRuntime):
        cap = cv2.VideoCapture(rt.path)
        if not cap.isOpened():
            rt.status = "error"
            return
        rt.frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        rt.frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        rt.fps_src = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        rt.duration_sec = float((cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / max(1e-6, rt.fps_src))
        cap.release()

    def stop_camera(self, camera_id: int):
        with self._lock:
            rt = self.cameras.get(camera_id)
            if not rt:
                return
            rt._stop.set()
            rt.status = "stopped"

    def delete_camera(self, camera_id: int):
        with self._lock:
            rt = self.cameras.get(camera_id)

        if not rt:
            return False

        # останавливаем обработку
        rt._stop.set()
        rt.status = "deleted"

        # даём reader loop завершиться
        time.sleep(0.5)

        # очищаем аналитику и snapshots
        try:
            self.store.clear_camera(camera_id)
        except Exception:
            traceback.print_exc()

        # удаляем видеофайл
        try:
            if rt.path and os.path.exists(rt.path):
                os.remove(rt.path)
        except Exception:
            traceback.print_exc()

        # удаляем runtime из памяти
        with self._lock:
            self.cameras.pop(camera_id, None)

        return True

    def list_cameras(self) -> List[Dict[str, Any]]:
        with self._lock:
            cams = list(self.cameras.values())
        return [
            {"camera_id": c.camera_id, "name": c.name, "status": c.status,
             "w": c.frame_w, "h": c.frame_h, "fps_src": c.fps_src, "duration_sec": c.duration_sec}
            for c in cams
        ]

    def get_overlay(self, camera_id: int) -> Dict[str, Any]:
        with self._lock:
            rt = self.cameras.get(camera_id)
        if not rt:
            return {"ts": 0.0, "t_sec": 0.0, "detections": [], "config": {}}
        return rt.last_overlay

    def _get_camera_config_cached(self, rt: CameraRuntime) -> Dict[str, Any]:
        now = time.monotonic()
        if (now - rt._cfg_cache_ts) >= _CFG_CACHE_TTL or not rt._cfg_cache:
            rt._cfg_cache = self.store.get_camera_config(rt.camera_id)
            rt._cfg_cache_ts = now
        return rt._cfg_cache

    def invalidate_config_cache(self, camera_id: int):
        with self._lock:
            rt = self.cameras.get(camera_id)
        if rt:
            rt._cfg_cache = {}
            rt._cfg_cache_ts = 0.0

    # reader
    def _reader_loop(self, rt: CameraRuntime):
        cap = cv2.VideoCapture(rt.path)
        if not cap.isOpened():
            rt.status = "error"
            return
        interval = 1.0 / max(1e-6, float(SETTINGS.TARGET_FPS))
        raw_interval = 1.0 / max(1e-6, float(SETTINGS.RAW_STREAM_FPS))
        next_tick = time.monotonic()
        last_good_ts = 0.0

        while not rt._stop.is_set() and not self._stop_all.is_set():
            now = time.monotonic()
            if now < next_tick:
                time.sleep(next_tick - now)
            next_tick += interval

            ret, frame = cap.read()
            if not ret:
                rt.status = "ended"
                break

            t_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
            if t_msec and t_msec > 0:
                t_sec = float(t_msec) / 1000.0
                last_good_ts = t_sec
            else:
                last_good_ts += interval
                t_sec = last_good_ts

            t_wall = time.time()
            item = InferenceItem(camera_id=rt.camera_id, frame_bgr=frame, t_sec=t_sec, t_wall=t_wall)

            with rt._jpeg_lock:
                last_raw_ts = rt.last_jpeg_ts
            if (t_wall - last_raw_ts) >= raw_interval or rt.last_jpeg is None:
                ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                if ok:
                    with rt._jpeg_lock:
                        rt.last_jpeg = jpg.tobytes()
                        rt.last_jpeg_ts = t_wall

            try:
                if rt._q.full():
                    try:
                        rt._q.get_nowait()
                    except queue.Empty:
                        pass
                rt._q.put_nowait(item)
            except Exception:
                pass
        cap.release()

    #INFERENCE LOOP - вызывает ВСЕ модели
    def _infer_loop(self):
        annot_interval = 1.0 / max(1e-6, float(SETTINGS.ANNOT_STREAM_FPS))

        while not self._stop_all.is_set():
            try:
                items: List[InferenceItem] = []
                with self._lock:
                    cams = list(self.cameras.values())

                for rt in cams:
                    if rt.status != "running":
                        continue
                    try:
                        it = rt._q.get_nowait()
                        items.append(it)
                    except queue.Empty:
                        pass

                if not items:
                    time.sleep(0.003)
                    continue

                frames = [it.frame_bgr for it in items]

                #1. Person detection (COCO model)
                person_results = self.det.predict(frames, classes=None, max_det=120)

                #2. Object detection (trained model)
                obj_results_map: Dict[int, Any] = {}
                if self.obj_det is not None:
                    try:
                        obj_results = self.obj_det.predict(frames, classes=None, max_det=80)
                        for it2, or2 in zip(items, obj_results):
                            obj_results_map[it2.camera_id] = or2
                    except Exception as e:
                        print(f"OBJ inference error: {e}")

                #Pose detection
                pose_map: Dict[int, Any] = {}
                if self.pose_model is not None:
                    try:
                        pose_results = self.pose_model.predict(
                            frames, verbose=False,
                            device=self.det.ultra_device,
                            imgsz=SETTINGS.IMGSZ_DET,
                            conf=0.3, max_det=30,
                        )
                        for it2, pr2 in zip(items, pose_results):
                            pose_map[it2.camera_id] = pr2
                    except Exception as e:
                        print(f"POSE inference error: {e}")

                #4. Process each frame
                for it, person_r in zip(items, person_results):
                    with self._lock:
                        rt = self.cameras.get(it.camera_id)
                    if not rt:
                        continue

                    obj_r  = obj_results_map.get(it.camera_id)
                    pose_r = pose_map.get(it.camera_id)

                    overlay = self._process_frame(rt, it, person_r, obj_r, pose_r)
                    rt.last_overlay = overlay

                    if rt.last_timeline_sec < 0 or (it.t_sec - rt.last_timeline_sec) >= SETTINGS.TIMELINE_SAMPLE_SEC:
                        rt.last_timeline_sec = float(it.t_sec)
                        self.store.insert_camera_timeline_row(rt.camera_id, it.t_sec, overlay.get("counts", {}))

                    people = [d for d in overlay["detections"] if d.get("entity") == "person"]
                    self.state_rec.update(rt.camera_id, people, t_sec=it.t_sec)

                    with rt._jpeg_lock:
                        last_ann_ts = rt.last_annotated_jpeg_ts
                    if (it.t_wall - last_ann_ts) >= annot_interval or rt.last_annotated_jpeg is None:
                        fr2 = it.frame_bgr.copy()
                        draw_overlay_bgr(fr2, overlay)
                        ok2, jpg2 = cv2.imencode(".jpg", fr2, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                        if ok2:
                            with rt._jpeg_lock:
                                rt.last_annotated_jpeg = jpg2.tobytes()
                                rt.last_annotated_jpeg_ts = it.t_wall

            except Exception:
                traceback.print_exc()
                time.sleep(0.05)

    # _process_frame - принимает результаты ВСЕХ моделей
    def _process_frame(
        self, rt: CameraRuntime, it: InferenceItem,
        person_result, obj_result=None, pose_result=None,
    ) -> Dict[str, Any]:

        frame = it.frame_bgr
        h, w = frame.shape[:2]

        cfg = self._get_camera_config_cached(rt)
        exit_line = cfg.get("exit_line")
        exit_zone = cfg.get("exit_zone")

        #Person detections (из COCO модели)
        person_xyxy  = np.zeros((0, 4), dtype=np.float32)
        person_scores = np.zeros((0,), dtype=np.float32)
        person_cls    = np.zeros((0,), dtype=np.int32)

        if person_result.boxes is not None and len(person_result.boxes) > 0:
            all_xyxy   = person_result.boxes.xyxy.cpu().numpy().astype(np.float32)
            all_scores = person_result.boxes.conf.cpu().numpy().astype(np.float32)
            all_cls    = person_result.boxes.cls.cpu().numpy().astype(np.int32)

            names_map = getattr(person_result, "names", None) or getattr(self.det.model, "names", {})
            all_names = [str(names_map.get(int(c), str(int(c)))).strip().lower() for c in all_cls]

            # фильтруем только person
            p_idx = [i for i, nm in enumerate(all_names) if nm in SETTINGS.PERSON_CLASS_NAMES]
            if p_idx:
                person_xyxy   = all_xyxy[p_idx]
                person_scores = all_scores[p_idx]
                person_cls    = all_cls[p_idx]

        #Object detections (из обученной модели)
        obj_xyxy   = np.zeros((0, 4), dtype=np.float32)
        obj_scores = np.zeros((0,), dtype=np.float32)
        obj_cls    = np.zeros((0,), dtype=np.int32)
        obj_names_list: List[str] = []

        if obj_result is not None and obj_result.boxes is not None and len(obj_result.boxes) > 0:
            obj_xyxy   = obj_result.boxes.xyxy.cpu().numpy().astype(np.float32)
            obj_scores = obj_result.boxes.conf.cpu().numpy().astype(np.float32)
            obj_cls    = obj_result.boxes.cls.cpu().numpy().astype(np.int32)

            obj_names_map = getattr(obj_result, "names", None) or getattr(self.obj_det.model, "names", {})
            obj_names_list = [str(obj_names_map.get(int(c), str(int(c)))).strip().lower() for c in obj_cls]

            # Фильтруем по порогу уверенности в зависимости от класса:
            # погрузчик требует повышенного порога, чтобы не путаться с людьми
            keep = []
            for i, (nm, sc) in enumerate(zip(obj_names_list, obj_scores)):
                if "forklift" in nm:
                    if float(sc) >= SETTINGS.CONF_FORKLIFT:
                        keep.append(i)
                else:
                    if float(sc) >= SETTINGS.CONF_OBJ:
                        keep.append(i)

            if keep:
                keep = np.array(keep, dtype=np.int32)
                obj_xyxy       = obj_xyxy[keep]
                obj_scores     = obj_scores[keep]
                obj_cls        = obj_cls[keep]
                obj_names_list = [obj_names_list[i] for i in keep]
            else:
                obj_xyxy       = np.zeros((0, 4), dtype=np.float32)
                obj_scores     = np.zeros((0,),    dtype=np.float32)
                obj_cls        = np.zeros((0,),    dtype=np.int32)
                obj_names_list = []

        # Pose keypoints: сопоставляем по IoU bbox детекции с pose-боксом
        # pose_kpts_by_det: detection_index -> keypoints
        pose_kpts_by_det: Dict[int, List[List[float]]] = {}

        if pose_result is not None and len(person_xyxy) > 0:
            try:
                pose_kpts = None
                pose_boxes = None

                if hasattr(pose_result, "keypoints") and pose_result.keypoints is not None:
                    pose_kpts = pose_result.keypoints.data.cpu().numpy()
                if hasattr(pose_result, "boxes") and pose_result.boxes is not None and len(pose_result.boxes) > 0:
                    pose_boxes = pose_result.boxes.xyxy.cpu().numpy().astype(np.float32)

                if pose_kpts is not None and pose_boxes is not None and len(pose_kpts) > 0:
                    for pi in range(len(person_xyxy)):
                        det_box = person_xyxy[pi]
                        best_iou = 0.0
                        best_ki = -1

                        for ki in range(len(pose_boxes)):
                            pb = pose_boxes[ki]
                            ix1 = max(det_box[0], pb[0])
                            iy1 = max(det_box[1], pb[1])
                            ix2 = min(det_box[2], pb[2])
                            iy2 = min(det_box[3], pb[3])
                            inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
                            a1 = max(0.0, det_box[2] - det_box[0]) * max(0.0, det_box[3] - det_box[1])
                            a2 = max(0.0, pb[2] - pb[0]) * max(0.0, pb[3] - pb[1])
                            union = a1 + a2 - inter
                            iou = inter / union if union > 0 else 0.0
                            if iou > best_iou:
                                best_iou = iou
                                best_ki = ki

                        if best_iou > 0.2 and best_ki >= 0:
                            kpts = pose_kpts[best_ki]
                            pose_kpts_by_det[pi] = [
                                [float(kx), float(ky), float(kc)] for kx, ky, kc in kpts
                            ]
            except Exception:
                traceback.print_exc()

        #Tracking
        people_tracks = []
        object_tracks = []

        if len(person_xyxy) > 0:
            p_names = ["person"] * len(person_xyxy)
            people_tracks = rt.person_tracker.update(person_xyxy, person_scores, person_cls, p_names)

        if len(obj_xyxy) > 0:
            object_tracks = rt.obj_tracker.update(obj_xyxy, obj_scores, obj_cls, obj_names_list)

        # После трекинга сопоставляем keypoints с треками через IoU трека с детекциями
        # Это важно: порядок people_tracks НЕ совпадает с порядком person_xyxy
        pose_kpts_by_trackid: Dict[int, List[List[float]]] = {}
        if pose_kpts_by_det and len(person_xyxy) > 0:
            for pt in people_tracks:
                track_box = pt.to_xyxy()
                best_iou = 0.0
                best_det_idx = -1
                for di in range(len(person_xyxy)):
                    db = person_xyxy[di]
                    ix1 = max(track_box[0], db[0])
                    iy1 = max(track_box[1], db[1])
                    ix2 = min(track_box[2], db[2])
                    iy2 = min(track_box[3], db[3])
                    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
                    a1 = max(0.0, track_box[2] - track_box[0]) * max(0.0, track_box[3] - track_box[1])
                    a2 = max(0.0, db[2] - db[0]) * max(0.0, db[3] - db[1])
                    union = a1 + a2 - inter
                    iou = inter / union if union > 0 else 0.0
                    if iou > best_iou:
                        best_iou = iou
                        best_det_idx = di
                if best_iou > 0.15 and best_det_idx in pose_kpts_by_det:
                    pose_kpts_by_trackid[int(pt.track_id)] = pose_kpts_by_det[best_det_idx]

        # Object infos
        obj_infos: List[Dict[str, Any]] = []
        for ot in object_tracks:
            xyxy = ot.to_xyxy()
            obj_infos.append({
                "track_id": int(ot.track_id),
                "cls_name": str(ot.cls_name),
                "xyxy": tuple(map(float, xyxy)),
                "c": (float((xyxy[0] + xyxy[2]) / 2), float((xyxy[1] + xyxy[3]) / 2)),
            })

        now = float(it.t_wall)
        t_sec = float(it.t_sec)

        people_out: List[Dict[str, Any]] = []
        objects_out: List[Dict[str, Any]] = []

        # People processing
        for pt_i, pt in enumerate(people_tracks):
            x1, y1, x2, y2 = map(float, pt.to_xyxy())
            bh = max(1.0, y2 - y1)
            bbox_n = [x1 / w, y1 / h, x2 / w, y2 / h]
            person_xyxy_t = (x1, y1, x2, y2)

            fx = (x1 + x2) / 2.0 / w
            fy = y2 / h

            # exit zone
            in_exit = False
            if exit_zone and isinstance(exit_zone, list) and len(exit_zone) >= 3:
                poly = [(float(p[0]), float(p[1])) for p in exit_zone]
                in_exit = point_in_poly(fx, fy, poly)

            # exit line
            cur_side = None
            if exit_line and isinstance(exit_line, list) and len(exit_line) == 2:
                (ax, ay), (bx, by) = exit_line
                cur_side = float(line_side(fx, fy, float(ax), float(ay), float(bx), float(by)))

            # memory
            mem = rt.person_mem.get(pt.track_id)
            if mem is None:
                mem = {
                    "prev_side": None, "in_exit_since": None,
                    "was_in_exit": False, "carry_hits": 0,
                    "carry_obj": None, "carry_score": 0.0,
                }
                rt.person_mem[pt.track_id] = mem

            # line crossing
            if cur_side is not None:
                crossed = has_crossed(mem.get("prev_side"), cur_side)
                mem["prev_side"] = cur_side
                if crossed:
                    carrying_now = mem.get("carry_hits", 0) >= SETTINGS.CARRY_MIN_HITS
                    for ev in rt.emitter.line_cross_event(rt.camera_id, pt.track_id, now, carrying=carrying_now):
                        row = self.store.add_event(ev, frame_bgr=frame)
                        self._publish_event(row)

            # danger zone events
            if in_exit:
                if mem["in_exit_since"] is None:
                    mem["in_exit_since"] = t_sec
                mem["was_in_exit"] = True
                dwell = t_sec - float(mem["in_exit_since"])
                if dwell >= SETTINGS.EXIT_DWELL_SEC:
                    for ev in rt.emitter.exit_zone_event(rt.camera_id, pt.track_id, now):
                        row = self.store.add_event(ev, frame_bgr=frame)
                        self._publish_event(row)
                if dwell >= LOITER_THRESHOLD_SEC:
                    for ev in rt.emitter.loitering_event(rt.camera_id, pt.track_id, now, dwell):
                        row = self.store.add_event(ev, frame_bgr=frame)
                        self._publish_event(row)
            else:
                mem["in_exit_since"] = None

            # carrying (improved heuristic)
            kpts_px = pose_kpts_by_trackid.get(int(pt.track_id))

            best_obj = None
            best_score = 0.0

            for oi in obj_infos:
                score = _compute_carry_score(
                    person_xyxy_t, oi["xyxy"], oi["cls_name"],
                    keypoints_px=kpts_px,
                )
                if score > best_score:
                    best_score = score
                    best_obj = oi

            if best_score >= CARRY_SCORE_THRESHOLD:
                mem["carry_hits"] = min(SETTINGS.CARRY_MIN_HITS + 5, mem.get("carry_hits", 0) + 1)
                mem["carry_obj"] = {"track_id": best_obj["track_id"], "cls_name": best_obj["cls_name"]}
                mem["carry_score"] = best_score
            else:
                mem["carry_hits"] = max(0, mem.get("carry_hits", 0) - 1)
                if mem["carry_hits"] == 0:
                    mem["carry_obj"] = None
                    mem["carry_score"] = 0.0

            carrying = mem.get("carry_hits", 0) >= SETTINGS.CARRY_MIN_HITS and mem.get("carry_obj") is not None

            # carry_out event
            if carrying and in_exit:
                obj_label = mem["carry_obj"]["cls_name"] if mem.get("carry_obj") else "unknown"
                for ev in rt.emitter.carry_out_event(
                    rt.camera_id, pt.track_id, now, obj_label,
                    {"carry_obj": mem.get("carry_obj"), "bbox": bbox_n, "carry_score": mem.get("carry_score", 0)},
                ):
                    row = self.store.add_event(ev, frame_bgr=frame)
                    self._publish_event(row)

            # state
            if in_exit and carrying:
                state = "carrying_in_exit_zone"
            elif in_exit:
                state = "in_exit_zone"
            elif carrying:
                state = "carrying"
            else:
                state = "normal"

            # keypoints normalized for overlay
            kpts_norm = None
            if kpts_px is not None:
                kpts_norm = [[kx / w, ky / h, kc] for kx, ky, kc in kpts_px]

            person_dict: Dict[str, Any] = {
                "entity": "person", "track_id": int(pt.track_id),
                "bbox": bbox_n, "conf": float(pt.score),
                "in_exit_zone": in_exit, "carrying": carrying,
                "carry_obj": mem.get("carry_obj"), "state": state,
            }
            if kpts_norm is not None:
                person_dict["keypoints"] = kpts_norm

            people_out.append(person_dict)

        #Objects
        for ot in object_tracks:
            x1, y1, x2, y2 = map(float, ot.to_xyxy())
            objects_out.append({
                "entity": "object", "track_id": int(ot.track_id),
                "bbox": [x1 / w, y1 / h, x2 / w, y2 / h],
                "conf": float(ot.score), "cls_name": str(ot.cls_name),
            })

        #Forklift in danger zone
        for ot in object_tracks:
            cls_name = str(ot.cls_name).lower()
            if "forklift" not in cls_name:
                continue
            ox1, oy1, ox2, oy2 = map(float, ot.to_xyxy())
            ofx = (ox1 + ox2) / 2.0 / w
            ofy = oy2 / h
            fork_in_exit = False
            if exit_zone and isinstance(exit_zone, list) and len(exit_zone) >= 3:
                poly = [(float(p[0]), float(p[1])) for p in exit_zone]
                fork_in_exit = point_in_poly(ofx, ofy, poly)
            if fork_in_exit:
                fk_cx = (ox1 + ox2) / 2.0
                fk_cy = (oy1 + oy2) / 2.0
                fk_h = max(1.0, oy2 - oy1)
                has_pallet = any(
                    oi["cls_name"].lower() in ("pallet", "box")
                    and ((oi["c"][0] - fk_cx) ** 2 + (oi["c"][1] - fk_cy) ** 2) ** 0.5 < 1.5 * fk_h
                    for oi in obj_infos
                )
                for ev in rt.emitter.carry_out_event(
                    rt.camera_id, int(ot.track_id) + 10000, now,
                    "pallet_by_forklift" if has_pallet else "forklift_in_zone",
                    {"cls_name": cls_name, "has_pallet": has_pallet, "bbox": [ox1/w, oy1/h, ox2/w, oy2/h]},
                ):
                    row = self.store.add_event(ev, frame_bgr=frame)
                    self._publish_event(row)

        # Counts
        counts = {
            "people_total": len(people_out),
            "people_in_exit_zone": sum(1 for p in people_out if p["in_exit_zone"]),
            "people_carrying": sum(1 for p in people_out if p["carrying"]),
            "objects_total": len(objects_out),
        }

        return {
            "ts": now, "t_sec": t_sec,
            "config": {"exit_line": exit_line, "exit_zone": exit_zone},
            "detections": people_out + objects_out,
            "roi_detections": [], "counts": counts,
        }