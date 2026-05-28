import os
import json
import time
import queue
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.manager import CameraManager
from app.config import SNAPSHOT_DIR

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "media", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


class AckRequest(BaseModel):
    status: str  # "ack" | "false"
    note: str = ""


class CameraConfigRequest(BaseModel):
    exit_line: Optional[list] = None   # [[x,y],[x,y]]
    exit_zone: Optional[list] = None   # [[x,y],...]


@asynccontextmanager
async def lifespan(app: FastAPI):
    mgr = CameraManager(upload_dir=UPLOAD_DIR)
    app.state.mgr = mgr
    try:
        yield
    finally:
        mgr.shutdown()


app = FastAPI(title="AI-Detector Backend (Carry-Out MVP)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/snapshots", StaticFiles(directory=SNAPSHOT_DIR), name="snapshots")


def get_mgr(request: Request) -> CameraManager:
    mgr = getattr(request.app.state, "mgr", None)
    if mgr is None:
        raise HTTPException(status_code=500, detail="CameraManager not initialized")
    return mgr


@app.post("/api/cameras/upload")
async def upload_cameras(request: Request, files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files")

    mgr = get_mgr(request)

    saved: List[tuple] = []
    for f in files:
        safe_name = os.path.basename(f.filename)
        tmp_path = os.path.join(UPLOAD_DIR, f"up_{int(time.time()*1000)}_{safe_name}")

        with open(tmp_path, "wb") as out:
            while True:
                chunk = await f.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)

        saved.append((f.filename, tmp_path))

    ids = mgr.add_videos(saved)
    return {"camera_ids": ids}


@app.get("/api/cameras")
def list_cameras(request: Request):
    return get_mgr(request).list_cameras()


@app.post("/api/cameras/{camera_id}/stop")
def stop_camera(request: Request, camera_id: int):
    get_mgr(request).stop_camera(camera_id)
    return {"ok": True}


@app.get("/api/camera/{camera_id}/config")
def get_camera_config(request: Request, camera_id: int):
    mgr = get_mgr(request)
    return mgr.store.get_camera_config(camera_id)


@app.post("/api/camera/{camera_id}/config")
def set_camera_config(request: Request, camera_id: int, req: CameraConfigRequest):
    mgr = get_mgr(request)
    row = mgr.store.set_camera_config(camera_id, req.exit_line, req.exit_zone)
    # сбрасываем кэш конфига чтобы pipeline сразу получил изменения
    mgr.invalidate_config_cache(camera_id)
    return {"config": row}


@app.post("/api/camera/{camera_id}/config/reset")
def reset_camera_config(request: Request, camera_id: int):
    mgr = get_mgr(request)
    row = mgr.store.set_camera_config(camera_id, exit_line=None, exit_zone=None)
    mgr.invalidate_config_cache(camera_id)
    return {"config": row}


@app.get("/api/overlay/{camera_id}")
def get_overlay(request: Request, camera_id: int):
    return get_mgr(request).get_overlay(camera_id)


def mjpeg_generator(packet_fn, camera_id: int, mgr: CameraManager):
    boundary = b"--frame"
    last_ts = -1.0

    while True:
        st = mgr.get_status(camera_id)
        if st in (None, "stopped", "ended", "error"):
            break

        ts, jpg = packet_fn(camera_id)
        if jpg is None or ts <= last_ts:
            time.sleep(0.01)
            continue

        last_ts = ts

        yield boundary + b"\r\n"
        yield b"Content-Type: image/jpeg\r\n"
        yield f"Content-Length: {len(jpg)}\r\n\r\n".encode("utf-8")
        yield jpg + b"\r\n"


@app.get("/api/stream/{camera_id}.mjpg")
def stream_mjpeg(request: Request, camera_id: int):
    mgr = get_mgr(request)
    return StreamingResponse(
        mjpeg_generator(mgr.get_jpeg_packet, camera_id, mgr),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/api/stream_annotated/{camera_id}.mjpg")
def stream_mjpeg_annotated(request: Request, camera_id: int):
    mgr = get_mgr(request)
    return StreamingResponse(
        mjpeg_generator(mgr.get_annotated_jpeg_packet, camera_id, mgr),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/api/events")
def get_events(request: Request, limit: int = 200, ack: str = "all", camera_id: Optional[int] = None):
    mgr = get_mgr(request)
    return {"events": mgr.store.list_events(limit=limit, ack=ack, camera_id=camera_id)}


@app.post("/api/events/{event_id}/ack")
def ack_event(request: Request, event_id: int, req: AckRequest):
    mgr = get_mgr(request)
    return {"event": mgr.store.set_ack(event_id, status=req.status, note=req.note)}


@app.get("/api/events/stream")
def events_stream(request: Request):
    mgr = get_mgr(request)
    sub_q = mgr.subscribe_events()

    def gen():
        try:
            yield "event: hello\ndata: {}\n\n"
            while True:
                try:
                    ev = sub_q.get(timeout=5.0)
                except queue.Empty:
                    yield "event: ping\ndata: {}\n\n"
                    continue
                yield f"event: event\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            mgr.unsubscribe_events(sub_q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/tracks")
def list_tracks(request: Request, camera_id: int):
    mgr = get_mgr(request)
    return {"camera_id": camera_id, "tracks": mgr.store.list_tracks(camera_id)}


@app.get("/api/track_timeline")
def track_timeline(request: Request, camera_id: int, track_id: int):
    mgr = get_mgr(request)
    return {"camera_id": camera_id, "track_id": track_id, "segments": mgr.store.get_track_timeline(camera_id, track_id)}


@app.get("/api/camera/kpi")
def camera_kpi(request: Request, camera_id: int):
    mgr = get_mgr(request)
    return {"kpi": mgr.store.get_camera_kpi(camera_id)}


@app.get("/api/camera/timeline")
def camera_timeline(request: Request, camera_id: int, limit: int = 2000):
    mgr = get_mgr(request)
    return {"timeline": mgr.store.get_camera_timeline(camera_id, limit=limit)}


@app.post("/api/camera/{camera_id}/clear")
def clear_camera_analytics(request: Request, camera_id: int):
    mgr = get_mgr(request)
    # очищаем аналитику
    deleted = mgr.store.clear_camera(camera_id)
    # также сбрасываем конфиг зон
    mgr.store.set_camera_config(camera_id, exit_line=None, exit_zone=None)
    mgr.invalidate_config_cache(camera_id)
    return {"ok": True, "deleted": deleted}