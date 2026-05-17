import os
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import queue

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from .config import SETTINGS
from .analytics.pose import classify_pose_static, check_hand_raised
from .analytics.tracker import SimpleTracker, update_motion, is_walking
from .analytics.rules import EventEmitter
from .analytics.visualize import draw_overlay_bgr
from .storage.store import AnalyticsStore

def select_device(requested: str = "auto") -> str:
    if requested == "auto":
        if torch.cuda.is_available():
            return "cuda:0"
        return "cpu"
    if requested.startswith("cuda") and torch.cuda.is_available():
        return requested
    if requested == "cpu":
        return "cpu"
    return "cpu"

@dataclass
class CameraRuntime:
    camera_id: int
    name: str
    path: str
    status: str = "running"  # running/ended/stopped/error

    frame_w: int = 0
    frame_h: int = 0
    fps_src: float = 30.0

    last_timeline_sec: float = -1.0
    last_jpeg: Optional[bytes] = None
    last_frame_bgr: Optional[np.ndarray] = None
    last_overlay: Dict[str, Any] = field(default_factory=lambda: {"ts": 0.0, "detections": []})

    _q: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=1))
    _stop: threading.Event = field(default_factory=threading.Event)

    tracker: SimpleTracker = field(default_factory=SimpleTracker)
    emitter: EventEmitter = field(default_factory=EventEmitter)

@dataclass
class InferenceItem:
    camera_id: int
    frame_bgr: np.ndarray
    t_video: float
    t_wall: float

class TrackStateRecorder:
    """
    Записывает сегменты состояний (base_pose) в SQLite:
      (start_sec, end_sec, state) для каждого track_id.
    Делает мало записей: start на смене, end обновляет раз в STATE_DB_UPDATE_SEC.
    """
    def __init__(self, store: AnalyticsStore):
        self.store = store
        self._lock = threading.Lock()
        # (camera_id, track_id) -> dict
        self.active: Dict[Tuple[int,int], Dict[str, Any]] = {}

    def update(self, camera_id: int, detections: List[Dict[str, Any]], t_sec: float):
        now = float(t_sec)
        seen_keys = set()

        with self._lock:
            for det in detections:
                tid = int(det["track_id"])
                state = str(det.get("base_pose", det.get("pose", "unknown")))

                key = (int(camera_id), int(tid))
                seen_keys.add(key)

                cur = self.active.get(key)

                if cur is None:
                    seg_id = self.store.start_segment(camera_id, tid, state, now)
                    self.active[key] = {
                        "seg_id": seg_id,
                        "state": state,
                        "last_seen": now,
                        "last_db_update": now,
                    }
                    continue

                cur["last_seen"] = now

                if state != cur["state"]:
                    # закрыть старый сегмент на текущем времени
                    self.store.update_segment_end(cur["seg_id"], now)
                    # начать новый
                    seg_id = self.store.start_segment(camera_id, tid, state, now)
                    cur["seg_id"] = seg_id
                    cur["state"] = state
                    cur["last_db_update"] = now
                else:
                    # периодически обновлять end_sec текущего сегмента
                    if (now - cur["last_db_update"]) >= SETTINGS.STATE_DB_UPDATE_SEC:
                        self.store.update_segment_end(cur["seg_id"], now)
                        cur["last_db_update"] = now

            # закрыть треки, которые пропали
            to_close = []
            for key, cur in self.active.items():
                if key in seen_keys:
                    continue
                if (now - cur["last_seen"]) >= SETTINGS.STATE_MISS_GAP_SEC:
                    to_close.append((key, cur))

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

        self.device = select_device(SETTINGS.DEVICE)
        self.ultra_device = 0 if self.device.startswith("cuda") else "cpu"

        self.model = YOLO(SETTINGS.MODEL_NAME)

        self.use_half = False
        if self.device.startswith("cuda"):
            cap = torch.cuda.get_device_capability(0)
            self.use_half = (cap[0] >= 7)
            dummy = np.zeros((SETTINGS.IMGSZ, SETTINGS.IMGSZ, 3), dtype=np.uint8)
            _ = self.model.predict(dummy, verbose=False, device=self.ultra_device, imgsz=SETTINGS.IMGSZ, half=self.use_half)

        self._infer_thread = threading.Thread(target=self._infer_loop, daemon=True)
        self._infer_thread.start()

    def add_videos(self, files: List[Tuple[str, bytes]]) -> List[int]:
        ids: List[int] = []
        with self._lock:
            if len(self.cameras) + len(files) > SETTINGS.MAX_CAMERAS:
                raise ValueError(f"Слишком много камер. Максимум {SETTINGS.MAX_CAMERAS}")

        for filename, content in files:
            camera_id = self._alloc_id()
            safe_name = f"cam{camera_id}_{os.path.basename(filename)}"
            path = os.path.join(self.upload_dir, safe_name)
            with open(path, "wb") as f:
                f.write(content)

            rt = CameraRuntime(camera_id=camera_id, name=safe_name, path=path)
            self._init_capture_meta(rt)

            with self._lock:
                self.cameras[camera_id] = rt

            t = threading.Thread(target=self._reader_loop, args=(rt,), daemon=True)
            t.start()
            ids.append(camera_id)

        return ids

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
        cap.release()

    def stop_camera(self, camera_id: int):
        with self._lock:
            rt = self.cameras.get(camera_id)
            if not rt:
                return
            rt._stop.set()
            rt.status = "stopped"

    def list_cameras(self) -> List[Dict[str, Any]]:
        with self._lock:
            cams = list(self.cameras.values())
        return [{
            "camera_id": c.camera_id,
            "name": c.name,
            "status": c.status,
            "w": c.frame_w,
            "h": c.frame_h,
            "fps_src": c.fps_src,
        } for c in cams]

    def get_overlay(self, camera_id: int) -> Dict[str, Any]:
        rt = self.cameras.get(camera_id)
        if not rt:
            return {"ts": 0.0, "detections": []}
        return rt.last_overlay

    def get_jpeg(self, camera_id: int) -> Optional[bytes]:
        rt = self.cameras.get(camera_id)
        if not rt:
            return None
        return rt.last_jpeg

    def get_annotated_jpeg(self, camera_id: int) -> Optional[bytes]:
        rt = self.cameras.get(camera_id)
        if not rt or rt.last_frame_bgr is None:
            return None

        frame = rt.last_frame_bgr.copy()
        draw_overlay_bgr(frame, rt.last_overlay)

        ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not ok:
            return None
        return jpg.tobytes()

    # -------- threads --------
    def _reader_loop(self, rt: CameraRuntime):
        cap = cv2.VideoCapture(rt.path)
        if not cap.isOpened():
            rt.status = "error"
            return

        interval = 1.0 / float(SETTINGS.TARGET_FPS)
        next_tick = time.monotonic()

        frame_idx = 0
        while not rt._stop.is_set():
            now = time.monotonic()
            if now < next_tick:
                time.sleep(next_tick - now)
            next_tick += interval

            ret, frame = cap.read()
            if not ret:
                rt.status = "ended"
                break

            frame_idx += 1
            t_video = float(frame_idx) / float(SETTINGS.TARGET_FPS)
            item = InferenceItem(camera_id=rt.camera_id, frame_bgr=frame, t_video=t_video, t_wall=time.time())

            try:
                if rt._q.full():
                    _ = rt._q.get_nowait()
                rt._q.put_nowait(item)
            except Exception:
                pass

        cap.release()

    def _infer_loop(self):
        while True:
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
                time.sleep(0.005)
                continue

            frames = [it.frame_bgr for it in items]

            try:
                results = self.model.predict(
                    frames,
                    verbose=False,
                    device=self.ultra_device,
                    imgsz=SETTINGS.IMGSZ,
                    conf=SETTINGS.CONF,
                    iou=SETTINGS.IOU,
                    half=self.use_half,
                    classes=[0],
                    max_det=50,
                )
            except Exception:
                for it in items:
                    rt = self.cameras.get(it.camera_id)
                    if rt:
                        rt.status = "error"
                time.sleep(0.1)
                continue

            for it, r in zip(items, results):
                rt = self.cameras.get(it.camera_id)
                if not rt:
                    continue

                detections = self._postprocess(rt, r, it)

                if rt.last_timeline_sec < 0 or (it.t_video - rt.last_timeline_sec) >= SETTINGS.TIMELINE_SAMPLE_SEC:
                    rt.last_timeline_sec = float(it.t_video)

                    counts = {
                        "total_people": len(detections),
                        "standing": 0, "walking": 0, "sitting": 0, "lying": 0, "unknown": 0,
                        "hand_raised": 0,
                    }

                    for d in detections:
                        bp = d.get("base_pose", d.get("pose", "unknown"))
                        if bp in counts:
                            counts[bp] += 1
                        else:
                            counts["unknown"] += 1
                        if d.get("has_hand_raised", False):
                            counts["hand_raised"] += 1

                    self.store.insert_camera_timeline_row(rt.camera_id, it.t_video, counts)

                rt.last_overlay = {"ts": it.t_wall, "detections": detections}
                rt.last_frame_bgr = it.frame_bgr

                # ВАЖНО: пишем сегменты состояний в SQLite
                self.state_rec.update(rt.camera_id, detections, t_sec=it.t_video)

                # events -> SQLite (+snapshot)
                new_events = rt.emitter.update(rt.camera_id, detections, it.t_wall)
                for ev in new_events:
                    self.store.add_event(ev, frame_bgr=it.frame_bgr)

                ok, jpg = cv2.imencode(".jpg", it.frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ok:
                    rt.last_jpeg = jpg.tobytes()

    def _postprocess(self, rt: CameraRuntime, r, it: InferenceItem) -> List[Dict[str, Any]]:
        fh, fw = it.frame_bgr.shape[:2]
        h = max(1, int(fh))
        w = max(1, int(fw))
        rt.frame_w = w
        rt.frame_h = h

        if r.boxes is None or len(r.boxes) == 0:
            return []
        if r.keypoints is None:
            return []

        boxes_xyxy = r.boxes.xyxy.cpu().numpy().astype(np.float32)
        kps_xy = r.keypoints.xy.cpu().numpy().astype(np.float32)      # (N,17,2) pixels
        kps_cf = r.keypoints.conf.cpu().numpy().astype(np.float32)    # (N,17)

        det_bboxes = [boxes_xyxy[i] for i in range(len(boxes_xyxy))]
        assignments = rt.tracker.update(det_bboxes)
        det_to_track: Dict[int, Any] = {di: tr for tr, di in assignments}

        out: List[Dict[str, Any]] = []

        for di in range(len(det_bboxes)):
            tr = det_to_track.get(di)
            if tr is None:
                continue

            bbox = det_bboxes[di]
            kxy = kps_xy[di]
            confs = kps_cf[di]

            update_motion(tr, t_sec=it.t_video)

            base_pose = classify_pose_static(kxy, confs, bbox)
            if base_pose == "standing" and is_walking(tr):
                base_pose = "walking"
            base_pose = tr.pose_h.apply(base_pose)

            prev_hand_state = bool(tr.hand_h.state)
            raw_hand = check_hand_raised(kxy, confs, bbox, currently_raised=prev_hand_state)
            has_hand = tr.hand_h.apply(raw_hand)

            display_pose = "hand_raised" if has_hand else base_pose

            x1, y1, x2, y2 = map(float, bbox)
            bbox_n = [x1 / w, y1 / h, x2 / w, y2 / h]

            kp_n = []
            for j in range(kxy.shape[0]):
                kp_n.append([float(kxy[j][0] / w), float(kxy[j][1] / h), float(confs[j])])

            out.append({
                "track_id": int(tr.id),
                "pose": display_pose,
                "base_pose": base_pose,
                "has_hand_raised": bool(has_hand),
                "bbox": bbox_n,
                "keypoints": kp_n,
            })

        return out