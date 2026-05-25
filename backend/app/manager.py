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
from .pipeline.visualize import draw_overlay_bgr, draw_zones_only_bgr
from .pipeline.trackers import ByteTracker

cv2.setNumThreads(0)


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
    status: str = "running"  # running/ended/stopped/error

    frame_w: int = 0
    frame_h: int = 0
    fps_src: float = 30.0
    duration_sec: float = 0.0

    last_overlay: Dict[str, Any] = field(default_factory=lambda: {"ts": 0.0, "t_sec": 0.0, "detections": [], "config": {}})
    last_jpeg: Optional[bytes] = None
    last_annotated_jpeg: Optional[bytes] = None
    last_frame_bgr: Optional[np.ndarray] = None

    last_jpeg_ts: float = 0.0
    last_annotated_jpeg_ts: float = 0.0

    last_timeline_sec: float = -1.0

    _q: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=1))
    _stop: threading.Event = field(default_factory=threading.Event)

    # trackers
    person_tracker: ByteTracker = field(default_factory=lambda: ByteTracker(track_thresh=SETTINGS.CONF_DET, match_iou_thr=0.7, max_age=25))
    obj_tracker: ByteTracker = field(default_factory=lambda: ByteTracker(track_thresh=SETTINGS.CONF_DET, match_iou_thr=0.7, max_age=35))

    person_mem: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    emitter: EventEmitter = field(default_factory=EventEmitter)


class TrackStateRecorder:
    def __init__(self, store: AnalyticsStore):
        self.store = store
        self._lock = threading.Lock()
        self.active: Dict[Tuple[int, int], Dict[str, Any]] = {}

    def update(self, camera_id: int, people: List[Dict[str, Any]], t_sec: float):
        now = float(t_sec)
        seen = set()

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
                    cur["seg_id"] = seg_id
                    cur["state"] = state
                    cur["last_db"] = now
                else:
                    if (now - cur["last_db"]) >= SETTINGS.STATE_DB_UPDATE_SEC:
                        self.store.update_segment_end(cur["seg_id"], now)
                        cur["last_db"] = now

            to_close = []
            for key, cur in self.active.items():
                if key in seen:
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

        self.det = YOLODetector(
            model_path=SETTINGS.MODEL_DET,
            device=SETTINGS.DEVICE,
            imgsz=SETTINGS.IMGSZ_DET,
            conf=SETTINGS.CONF_DET,
            iou=SETTINGS.IOU_DET,
        )

        roi_model = None
        if SETTINGS.MODEL_ROI.strip():
            roi_model = YOLODetector(
                model_path=SETTINGS.MODEL_ROI.strip(),
                device=SETTINGS.DEVICE,
                imgsz=SETTINGS.IMGSZ_ROI,
                conf=SETTINGS.CONF_DET,
                iou=SETTINGS.IOU_DET,
            )
        self.roi = ROIPipeline(det=self.det, roi_det=roi_model)

        self._stop_all = threading.Event()
        self._infer_thread = threading.Thread(target=self._infer_loop, daemon=True)
        self._infer_thread.start()

        self._subs_lock = threading.Lock()
        self._event_subs: List[queue.Queue] = []

        print("MODEL_DET:", SETTINGS.MODEL_DET)
        print("MODEL names:", getattr(self.det.model, "names", None))
        print("PERSON_CLASS_NAMES:", SETTINGS.PERSON_CLASS_NAMES)
        print("OBJECT_CLASS_NAMES:", SETTINGS.OBJECT_CLASS_NAMES)
        print("CONF_DET:", SETTINGS.CONF_DET, "IMGSZ_DET:", SETTINGS.IMGSZ_DET)

    # ---------- stream helpers ----------
    def get_status(self, camera_id: int) -> Optional[str]:
        with self._lock:
            rt = self.cameras.get(camera_id)
            return rt.status if rt else None

    def get_jpeg_packet(self, camera_id: int) -> Tuple[float, Optional[bytes]]:
        with self._lock:
            rt = self.cameras.get(camera_id)
            if not rt:
                return 0.0, None
            return float(rt.last_jpeg_ts), rt.last_jpeg

    def get_annotated_jpeg_packet(self, camera_id: int) -> Tuple[float, Optional[bytes]]:
        with self._lock:
            rt = self.cameras.get(camera_id)
            if not rt:
                return 0.0, None
            return float(rt.last_annotated_jpeg_ts), rt.last_annotated_jpeg

    # ---------- lifecycle ----------
    def shutdown(self):
        self._stop_all.set()
        with self._lock:
            for rt in self.cameras.values():
                rt._stop.set()
                rt.status = "stopped"

    # ---------- SSE ----------
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
        for q in subs:
            try:
                q.put_nowait(ev)
            except Exception:
                self.unsubscribe_events(q)

    # ---------- cameras ----------
    def add_videos(self, files: List[Tuple[str, str]]) -> List[int]:
        ids: List[int] = []
        with self._lock:
            if len(self.cameras) + len(files) > SETTINGS.MAX_CAMERAS:
                raise ValueError(f"Слишком много камер. Максимум {SETTINGS.MAX_CAMERAS}")

        for orig_name, path in files:
            camera_id = self._alloc_id()
            safe_name = f"cam{camera_id}_{os.path.basename(orig_name)}"

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
        rt.duration_sec = float((cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / max(1e-6, rt.fps_src))
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
            "duration_sec": c.duration_sec,
        } for c in cams]

    def get_overlay(self, camera_id: int) -> Dict[str, Any]:
        with self._lock:
            rt = self.cameras.get(camera_id)
        if not rt:
            return {"ts": 0.0, "t_sec": 0.0, "detections": [], "config": {}}
        return rt.last_overlay

    # ---------- threads ----------
    def _reader_loop(self, rt: CameraRuntime):
        cap = cv2.VideoCapture(rt.path)
        if not cap.isOpened():
            rt.status = "error"
            return

        interval = 1.0 / max(1e-6, float(SETTINGS.TARGET_FPS))
        next_tick = time.monotonic()
        last_good_ts = 0.0

        while (not rt._stop.is_set()) and (not self._stop_all.is_set()):
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

            # raw stream jpeg (НЕ tight-loop, обновляется раз в кадр)
            rt.last_frame_bgr = frame
            ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            if ok:
                rt.last_jpeg = jpg.tobytes()
                rt.last_jpeg_ts = t_wall

            try:
                if rt._q.full():
                    _ = rt._q.get_nowait()
                rt._q.put_nowait(item)
            except Exception:
                pass

        cap.release()

    def _infer_loop(self):
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

                try:
                    results = self.det.predict(frames, classes=None, max_det=120)
                except Exception:
                    with self._lock:
                        for it in items:
                            rt = self.cameras.get(it.camera_id)
                            if rt:
                                rt.status = "error"
                    time.sleep(0.05)
                    continue

                for it, r in zip(items, results):
                    with self._lock:
                        rt = self.cameras.get(it.camera_id)
                    if not rt:
                        continue

                    try:
                        overlay = self._process_frame(rt, it, r)
                    except Exception:
                        traceback.print_exc()
                        rt.status = "error"
                        continue

                    rt.last_overlay = overlay

                    # timeline sample
                    if rt.last_timeline_sec < 0 or (it.t_sec - rt.last_timeline_sec) >= SETTINGS.TIMELINE_SAMPLE_SEC:
                        rt.last_timeline_sec = float(it.t_sec)
                        counts = overlay.get("counts", {})
                        self.store.insert_camera_timeline_row(rt.camera_id, it.t_sec, counts)

                    # segments
                    people = [d for d in overlay["detections"] if d.get("entity") == "person"]
                    self.state_rec.update(rt.camera_id, people, t_sec=it.t_sec)

                    # annotated jpeg
                    fr2 = it.frame_bgr.copy()
                    draw_overlay_bgr(fr2, overlay)
                    ok2, jpg2 = cv2.imencode(".jpg", fr2, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                    if ok2:
                        rt.last_annotated_jpeg = jpg2.tobytes()
                        rt.last_annotated_jpeg_ts = it.t_wall

            except Exception:
                # чтобы поток инференса не умер навсегда
                traceback.print_exc()
                time.sleep(0.1)

    def _process_frame(self, rt: CameraRuntime, it: InferenceItem, r) -> Dict[str, Any]:
        frame = it.frame_bgr
        h, w = frame.shape[:2]
        rt.frame_w = int(w)
        rt.frame_h = int(h)

        cfg = self.store.get_camera_config(rt.camera_id)
        exit_line = cfg.get("exit_line")
        exit_zone = cfg.get("exit_zone")

        dets_xyxy = np.zeros((0, 4), dtype=np.float32)
        det_scores = np.zeros((0,), dtype=np.float32)
        det_cls = np.zeros((0,), dtype=np.int32)

        if r.boxes is not None and len(r.boxes) > 0:
            dets_xyxy = r.boxes.xyxy.cpu().numpy().astype(np.float32)
            det_scores = r.boxes.conf.cpu().numpy().astype(np.float32)
            det_cls = r.boxes.cls.cpu().numpy().astype(np.int32)

        names_map = getattr(r, "names", None) or getattr(self.det.model, "names", {})
        det_names = [str(names_map.get(int(c), str(int(c)))).strip().lower() for c in det_cls]

        person_idx = [i for i, nm in enumerate(det_names) if nm in SETTINGS.PERSON_CLASS_NAMES]
        obj_idx = [i for i, nm in enumerate(det_names) if nm in SETTINGS.OBJECT_CLASS_NAMES]

        people_tracks = []
        object_tracks = []

        if len(person_idx) > 0:
            p_xyxy = dets_xyxy[person_idx]
            p_sc = det_scores[person_idx]
            p_cl = det_cls[person_idx]
            p_nm = [det_names[i] for i in person_idx]
            people_tracks = rt.person_tracker.update(p_xyxy, p_sc, p_cl, p_nm)

        if len(obj_idx) > 0:
            o_xyxy = dets_xyxy[obj_idx]
            o_sc = det_scores[obj_idx]
            o_cl = det_cls[obj_idx]
            o_nm = [det_names[i] for i in obj_idx]
            object_tracks = rt.obj_tracker.update(o_xyxy, o_sc, o_cl, o_nm)

        people_for_roi: List[Dict[str, Any]] = []
        people_out: List[Dict[str, Any]] = []
        objects_out: List[Dict[str, Any]] = []

        obj_infos = []
        for ot in object_tracks:
            xyxy = ot.to_xyxy()
            cx = float((xyxy[0] + xyxy[2]) / 2.0)
            cy = float((xyxy[1] + xyxy[3]) / 2.0)
            obj_infos.append({
                "track_id": int(ot.track_id),
                "cls_name": str(ot.cls_name),
                "conf": float(ot.score),
                "xyxy": xyxy,
                "c": (cx, cy)
            })

        now = float(it.t_wall)
        t_sec = float(it.t_sec)

        for pt in people_tracks:
            xyxy = pt.to_xyxy()
            x1, y1, x2, y2 = map(float, xyxy)
            bh = max(1.0, y2 - y1)

            bbox_n = [x1 / w, y1 / h, x2 / w, y2 / h]

            fx = (x1 + x2) / 2.0 / w
            fy = y2 / h

            in_exit = False
            if exit_zone and isinstance(exit_zone, list) and len(exit_zone) >= 3:
                poly = [(float(p[0]), float(p[1])) for p in exit_zone]
                in_exit = point_in_poly(float(fx), float(fy), poly)

            cur_side = None
            crossed = False
            if exit_line and isinstance(exit_line, list) and len(exit_line) == 2:
                (ax, ay), (bx, by) = exit_line
                cur_side = float(line_side(float(fx), float(fy), float(ax), float(ay), float(bx), float(by)))

            mem = rt.person_mem.get(pt.track_id)
            if mem is None:
                mem = {
                    "prev_side": None,
                    "in_exit_since": None,
                    "was_in_exit": False,
                    "carry_hits": 0,
                    "carry_obj": None,
                }
                rt.person_mem[pt.track_id] = mem

            if cur_side is not None:
                crossed = has_crossed(mem.get("prev_side"), cur_side)
                mem["prev_side"] = cur_side

            if in_exit:
                if mem["in_exit_since"] is None:
                    mem["in_exit_since"] = t_sec
                mem["was_in_exit"] = True
                if (t_sec - float(mem["in_exit_since"])) >= SETTINGS.EXIT_DWELL_SEC:
                    for ev in rt.emitter.exit_zone_event(rt.camera_id, pt.track_id, now):
                        snap = frame.copy()
                        draw_zones_only_bgr(snap, exit_line, exit_zone)
                        row = self.store.add_event(ev, frame_bgr=snap)
                        self._publish_event(row)
            else:
                mem["in_exit_since"] = None

            carrying = False
            carry_obj = mem.get("carry_obj")
            best = None
            best_d = 1e18

            pcx = float((x1 + x2) / 2.0)
            pcy = float((y1 + y2) / 2.0)

            for oi in obj_infos:
                ocx, ocy = oi["c"]
                d = ((ocx - pcx) ** 2 + (ocy - pcy) ** 2) ** 0.5
                if d < best_d:
                    best_d = d
                    best = oi

            if best is not None and best_d < (SETTINGS.CARRY_ASSOC_DIST_RATIO * bh):
                if carry_obj is None or int(carry_obj.get("track_id")) == int(best["track_id"]):
                    mem["carry_hits"] = int(mem.get("carry_hits", 0)) + 1
                else:
                    mem["carry_hits"] = 1
                mem["carry_obj"] = {"track_id": int(best["track_id"]), "cls_name": best["cls_name"]}
            else:
                mem["carry_hits"] = max(0, int(mem.get("carry_hits", 0)) - 1)
                if mem["carry_hits"] == 0:
                    mem["carry_obj"] = None

            if int(mem.get("carry_hits", 0)) >= SETTINGS.CARRY_MIN_HITS and mem.get("carry_obj") is not None:
                carrying = True

            state = "normal"
            if in_exit and carrying:
                state = "carrying_in_exit_zone"
            elif in_exit:
                state = "in_exit_zone"
            elif carrying:
                state = "carrying"

            people_for_roi.append({
                "camera_id": rt.camera_id,
                "track_id": int(pt.track_id),
                "bbox_px": [int(x1), int(y1), int(x2), int(y2)],
                "in_exit_zone": bool(in_exit),
                "bh": float(bh)
            })

            people_out.append({
                "entity": "person",
                "track_id": int(pt.track_id),
                "bbox": bbox_n,
                "conf": float(pt.score),
                "in_exit_zone": bool(in_exit),
                "carrying": bool(carrying),
                "carry_obj": mem.get("carry_obj"),
                "state": state,
            })

            if carrying and mem.get("was_in_exit", False) and (crossed or (mem.get("in_exit_since") is None and not in_exit)):
                obj_label = (mem.get("carry_obj") or {}).get("cls_name", "object")
                payload = {"carry_obj": mem.get("carry_obj"), "crossed_line": bool(crossed), "t_sec": t_sec}
                for ev in rt.emitter.carry_out_event(rt.camera_id, pt.track_id, now, obj_label=obj_label, payload=payload):
                    snap = frame.copy()
                    draw_zones_only_bgr(snap, exit_line, exit_zone)
                    row = self.store.add_event(ev, frame_bgr=snap)
                    self._publish_event(row)
                mem["was_in_exit"] = False

        for ot in object_tracks:
            xyxy = ot.to_xyxy()
            x1, y1, x2, y2 = map(float, xyxy)
            bbox_n = [x1 / w, y1 / h, x2 / w, y2 / h]
            objects_out.append({
                "entity": "object",
                "track_id": int(ot.track_id),
                "bbox": bbox_n,
                "conf": float(ot.score),
                "cls_name": str(ot.cls_name),
            })

        roi_dets = []
        if SETTINGS.ROI_ENABLED:
            cand = people_for_roi
            if SETTINGS.ROI_ONLY_NEAR_EXIT_ZONE:
                cand = [p for p in cand if p.get("in_exit_zone")]
            cand = [p for p in cand if float(p.get("bh", 9999)) <= 260.0 and float(p.get("bh", 9999)) >= SETTINGS.ROI_MIN_PERSON_H_PX]
            crops = self.roi.build_crops(frame, cand)
            roi_dets = self.roi.run(crops)

        counts = {
            "people_total": len(people_out),
            "people_in_exit_zone": sum(1 for p in people_out if p.get("in_exit_zone")),
            "people_carrying": sum(1 for p in people_out if p.get("carrying")),
            "objects_total": len(objects_out),
        }

        overlay = {
            "ts": float(it.t_wall),
            "t_sec": float(it.t_sec),
            "config": {"exit_line": exit_line, "exit_zone": exit_zone},
            "detections": people_out + objects_out,
            "roi_detections": roi_dets,
            "counts": counts,
            "debug": {
                "raw_det_total": int(len(det_cls)),
                "raw_person_total": int(len(person_idx)),
                "raw_obj_total": int(len(obj_idx)),
                "tracked_person_total": int(len(people_tracks)),
                "tracked_obj_total": int(len(object_tracks)),
                "conf_det": float(SETTINGS.CONF_DET),
            }
        }
        return overlay