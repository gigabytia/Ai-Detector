import os
import sqlite3
import threading
from typing import Optional, List, Dict, Any, Tuple

import cv2
import numpy as np

from ..config import DB_PATH, SNAPSHOT_DIR

class AnalyticsStore:
    """
    SQLite store:
      - events
      - track_segments
      - camera_timeline (люди/позы по времени для камеры)
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            cur = self.conn.cursor()

            # events
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
                ack_status TEXT NOT NULL DEFAULT 'unacked',
                ack_ts REAL,
                ack_note TEXT
            )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_events_cam ON events(camera_id, ts DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_events_ack ON events(ack_status)")

            # segments (таймлайн состояний по трекам)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS track_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id INTEGER NOT NULL,
                track_id INTEGER NOT NULL,
                state TEXT NOT NULL,
                start_sec REAL NOT NULL,
                end_sec REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_seg_cam_track ON track_segments(camera_id, track_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_seg_time ON track_segments(camera_id, start_sec, end_sec)")

            # camera timeline (люди/позы по времени)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS camera_timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id INTEGER NOT NULL,
                t_sec REAL NOT NULL,
                total_people INTEGER NOT NULL,
                standing INTEGER NOT NULL,
                walking INTEGER NOT NULL,
                sitting INTEGER NOT NULL,
                lying INTEGER NOT NULL,
                hand_raised INTEGER NOT NULL,
                unknown INTEGER NOT NULL
            )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cam_timeline ON camera_timeline(camera_id, t_sec)")

            self.conn.commit()

    # ---------------- events ----------------
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

        if frame_bgr is not None:
            os.makedirs(SNAPSHOT_DIR, exist_ok=True)
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

    def list_events(self, limit: int = 100, ack: str = "all", camera_id: Optional[int] = None) -> List[Dict[str, Any]]:
        limit = int(max(1, min(limit, 2000)))
        ack = str(ack)

        q = "SELECT * FROM events"
        params = []
        where = []

        if ack != "all":
            where.append("ack_status=?")
            params.append(ack)

        if camera_id is not None:
            where.append("camera_id=?")
            params.append(int(camera_id))

        if where:
            q += " WHERE " + " AND ".join(where)

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

    # ---------------- segments ----------------
    def start_segment(self, camera_id: int, track_id: int, state: str, start_sec: float) -> int:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO track_segments (camera_id, track_id, state, start_sec, end_sec)
                VALUES (?, ?, ?, ?, ?)
            """, (int(camera_id), int(track_id), str(state), float(start_sec), float(start_sec)))
            seg_id = int(cur.lastrowid)
            self.conn.commit()
        return seg_id

    def update_segment_end(self, seg_id: int, end_sec: float):
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("UPDATE track_segments SET end_sec=? WHERE id=?", (float(end_sec), int(seg_id)))
            self.conn.commit()

    def list_tracks(self, camera_id: int) -> List[int]:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT DISTINCT track_id
                FROM track_segments
                WHERE camera_id=?
                ORDER BY track_id
            """, (int(camera_id),))
            rows = cur.fetchall()
        return [int(r["track_id"]) for r in rows]

    def get_track_timeline(self, camera_id: int, track_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT id, camera_id, track_id, state, start_sec, end_sec
                FROM track_segments
                WHERE camera_id=? AND track_id=?
                ORDER BY start_sec
            """, (int(camera_id), int(track_id)))
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    # ---------------- camera timeline ----------------
    def insert_camera_timeline_row(self, camera_id: int, t_sec: float, counts: Dict[str, int]):
        row = (
            int(camera_id),
            float(t_sec),
            int(counts.get("total_people", 0)),
            int(counts.get("standing", 0)),
            int(counts.get("walking", 0)),
            int(counts.get("sitting", 0)),
            int(counts.get("lying", 0)),
            int(counts.get("hand_raised", 0)),
            int(counts.get("unknown", 0)),
        )
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO camera_timeline
                (camera_id, t_sec, total_people, standing, walking, sitting, lying, hand_raised, unknown)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row)
            self.conn.commit()

    def get_camera_timeline(self, camera_id: int, limit: int = 2000) -> List[Dict[str, Any]]:
        limit = int(max(1, min(limit, 20000)))
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT camera_id, t_sec, total_people, standing, walking, sitting, lying, hand_raised, unknown
                FROM camera_timeline
                WHERE camera_id=?
                ORDER BY t_sec DESC
                LIMIT ?
            """, (int(camera_id), limit))
            rows = cur.fetchall()
        # вернём по времени вперёд (удобно для графика)
        out = [dict(r) for r in rows]
        out.reverse()
        return out

    def get_camera_kpi(self, camera_id: int) -> Dict[str, Any]:
        cam = int(camera_id)

        with self._lock:
            cur = self.conn.cursor()

            cur.execute("""
                SELECT
                  COALESCE(MAX(t_sec), 0) as duration_sec,
                  COALESCE(AVG(total_people), 0) as avg_people,
                  COALESCE(MAX(total_people), 0) as max_people,
                  COUNT(*) as points
                FROM camera_timeline
                WHERE camera_id=?
            """, (cam,))
            a = dict(cur.fetchone())

            cur.execute("""
                SELECT COUNT(DISTINCT track_id) as unique_tracks
                FROM track_segments
                WHERE camera_id=?
            """, (cam,))
            b = dict(cur.fetchone())

            cur.execute("""
                SELECT COUNT(*) as events_total,
                       SUM(CASE WHEN ack_status='unacked' THEN 1 ELSE 0 END) as events_unacked
                FROM events
                WHERE camera_id=?
            """, (cam,))
            c = dict(cur.fetchone())

        return {
            "camera_id": cam,
            "duration_sec": float(a["duration_sec"] or 0),
            "avg_people": float(a["avg_people"] or 0),
            "max_people": int(a["max_people"] or 0),
            "timeline_points": int(a["points"] or 0),
            "unique_tracks": int(b["unique_tracks"] or 0),
            "events_total": int(c["events_total"] or 0),
            "events_unacked": int(c["events_unacked"] or 0),
        }
    def clear_camera(self, camera_id: int) -> Dict[str, int]:
        """
        Удаляет аналитику по конкретной камере:
          - camera_timeline
          - track_segments
          - events
        Возвращает количество удалённых строк.
        """
        cam = int(camera_id)

        with self._lock:
            cur = self.conn.cursor()

            cur.execute("SELECT COUNT(*) AS n FROM camera_timeline WHERE camera_id=?", (cam,))
            n_tl = int(cur.fetchone()["n"])

            cur.execute("SELECT COUNT(*) AS n FROM track_segments WHERE camera_id=?", (cam,))
            n_seg = int(cur.fetchone()["n"])

            cur.execute("SELECT COUNT(*) AS n FROM events WHERE camera_id=?", (cam,))
            n_ev = int(cur.fetchone()["n"])

            cur.execute("DELETE FROM camera_timeline WHERE camera_id=?", (cam,))
            cur.execute("DELETE FROM track_segments WHERE camera_id=?", (cam,))
            cur.execute("DELETE FROM events WHERE camera_id=?", (cam,))

            self.conn.commit()

        return {"timeline_deleted": n_tl, "segments_deleted": n_seg, "events_deleted": n_ev}