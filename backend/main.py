import os
from typing import List
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.manager import CameraManager
from app.config import SNAPSHOT_DIR

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "media", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="AI-Detector Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/snapshots", StaticFiles(directory=SNAPSHOT_DIR), name="snapshots")

mgr = CameraManager(upload_dir=UPLOAD_DIR)

class AckRequest(BaseModel):
    status: str  # "ack" | "false"
    note: str = ""

@app.post("/api/cameras/upload")
async def upload_cameras(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files")

    payload = []
    for f in files:
        payload.append((f.filename, await f.read()))

    try:
        ids = mgr.add_videos(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"camera_ids": ids}

@app.get("/api/cameras")
def list_cameras():
    return mgr.list_cameras()

@app.post("/api/cameras/{camera_id}/stop")
def stop_camera(camera_id: int):
    mgr.stop_camera(camera_id)
    return {"ok": True}

@app.get("/api/overlay/{camera_id}")
def get_overlay(camera_id: int):
    return mgr.get_overlay(camera_id)

@app.get("/api/events")
def get_events(limit: int = 100, ack: str = "all"):
    evs = mgr.store.list_events(limit=limit, ack=ack)
    return {"events": evs}

@app.post("/api/events/{event_id}/ack")
def ack_event(event_id: int, req: AckRequest):
    try:
        row = mgr.store.set_ack(event_id, status=req.status, note=req.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"event": row}

# ---- NEW: dashboard endpoints ----

@app.get("/api/tracks")
def list_tracks(camera_id: int):
    """
    Возвращает track_id, которые уже попали в таблицу track_segments.
    """
    return {"camera_id": camera_id, "tracks": mgr.store.list_tracks(camera_id)}

@app.get("/api/track_timeline")
def track_timeline(camera_id: int, track_id: int):
    """
    Сегменты состояний для выбранного трека.
    """
    segs = mgr.store.get_track_timeline(camera_id, track_id)
    return {"camera_id": camera_id, "track_id": track_id, "segments": segs}

# ---- streams ----

def mjpeg_generator(camera_id: int):
    boundary = b"--frame"
    import time as _t
    while True:
        jpg = mgr.get_jpeg(camera_id)
        if jpg is None:
            _t.sleep(0.05)
            continue
        yield boundary + b"\r\n"
        yield b"Content-Type: image/jpeg\r\n"
        yield f"Content-Length: {len(jpg)}\r\n\r\n".encode("utf-8")
        yield jpg + b"\r\n"

@app.get("/api/stream/{camera_id}.mjpg")
def stream_mjpeg(camera_id: int):
    return StreamingResponse(
        mjpeg_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

def mjpeg_annotated_generator(camera_id: int):
    boundary = b"--frame"
    import time as _t
    while True:
        jpg = mgr.get_annotated_jpeg(camera_id)
        if jpg is None:
            _t.sleep(0.05)
            continue
        yield boundary + b"\r\n"
        yield b"Content-Type: image/jpeg\r\n"
        yield f"Content-Length: {len(jpg)}\r\n\r\n".encode("utf-8")
        yield jpg + b"\r\n"

@app.get("/api/stream_annotated/{camera_id}.mjpg")
def stream_mjpeg_annotated(camera_id: int):
    return StreamingResponse(
        mjpeg_annotated_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/api/camera/kpi")
def camera_kpi(camera_id: int):
    return {"kpi": mgr.store.get_camera_kpi(camera_id)}

@app.get("/api/camera/timeline")
def camera_timeline(camera_id: int, limit: int = 2000):
    return {"timeline": mgr.store.get_camera_timeline(camera_id, limit=limit)}

@app.post("/api/camera/{camera_id}/clear")
def clear_camera_analytics(camera_id: int):
    info = mgr.store.clear_camera(camera_id)
    return {"ok": True, "deleted": info}