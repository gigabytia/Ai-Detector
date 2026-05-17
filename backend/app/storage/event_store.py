import os
import sqlite3
import threading
from typing import Optional, List, Dict, Any

import cv2
import numpy as np

from ..config import DB_PATH, SNAPSHOT_DIR

class EventStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id INTEGER NOT NULL,
                track_id INTEGER,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                ts REAL NOT NULL,
                text TEXT,
                snapshot_path TEXT,

                ack_status TEXT NOT NULL DEFAULT 'unacked',  -- unacked | ack | false
                ack_ts REAL,
                ack_note TEXT
            )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_events_ack ON events(ack_status)")
            self.conn.commit()

    def add_event(self, ev: Dict[str, Any], frame_bgr: Optional[np.ndarray] = None) -> Dict[str, Any]:
        camera_id = int(ev["camera_id"])
        track_id = ev.get("track_id", None)
        event_type = str(ev.get("event_type", "unknown"))
        severity = str(ev.get("severity", "info"))
        ts = float(ev["ts"])
        text = str(ev.get("text", ""))

        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO events (camera_id, track_id, event_type, severity, ts, text)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (camera_id, track_id, event_type, severity, ts, text))
            event_id = int(cur.lastrowid)
            self.conn.commit()

        snapshot_path = None
        if frame_bgr is not None:
            fn = f"event_{event_id}_cam{camera_id}_{int(ts)}.jpg"
            abs_path = os.path.join(SNAPSHOT_DIR, fn)

            ok, jpg = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            if ok:
                with open(abs_path, "wb") as f:
                    f.write(jpg.tobytes())
                snapshot_path = f"/snapshots/{fn}"

                with self._lock:
                    cur = self.conn.cursor()
                    cur.execute("UPDATE events SET snapshot_path=? WHERE id=?", (snapshot_path, event_id))
                    self.conn.commit()

        return self.get_event(event_id)

    def get_event(self, event_id: int) -> Dict[str, Any]:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT * FROM events WHERE id=?", (int(event_id),))
            row = cur.fetchone()
        return dict(row) if row else {}

    def list_events(self, limit: int = 100, ack: str = "all") -> List[Dict[str, Any]]:
        limit = int(max(1, min(limit, 1000)))
        ack = str(ack)

        q = "SELECT * FROM events"
        params = []

        if ack != "all":
            q += " WHERE ack_status=?"
            params.append(ack)

        q += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            cur = self.conn.cursor()
            cur.execute(q, tuple(params))
            rows = cur.fetchall()

        return [dict(r) for r in rows]

    def set_ack(self, event_id: int, status: str, note: str = "") -> Dict[str, Any]:
        status = str(status)
        if status not in ("ack", "false"):
            raise ValueError("status must be 'ack' or 'false'")

        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                UPDATE events
                SET ack_status=?, ack_ts=strftime('%s','now'), ack_note=?
                WHERE id=?
            """, (status, note, int(event_id)))
            self.conn.commit()

        return self.get_event(event_id)