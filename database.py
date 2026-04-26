import sqlite3
from pathlib import Path


class AnalyticsDB:
    def __init__(self, db_path="analytics.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        cur = self.conn.cursor()

        cur.execute("CREATE INDEX IF NOT EXISTS idx_timeline_run ON timeline(run_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tracks_run ON tracks(run_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            fps REAL,
            frame_width INTEGER,
            frame_height INTEGER,
            status TEXT,
            total_frames INTEGER,
            duration_sec REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            run_id INTEGER,
            track_id INTEGER,
            first_seen REAL,
            last_seen REAL,
            duration REAL,
            frames_seen INTEGER,
            dominant_pose TEXT,
            hand_raise_events INTEGER,
            avg_center_x REAL,
            avg_center_y REAL
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS timeline (
            run_id INTEGER,
            timestamp_sec REAL,
            total_people INTEGER,
            standing INTEGER,
            walking INTEGER,
            sitting INTEGER,
            lying INTEGER,
            hand_raised INTEGER,
            unknown INTEGER
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            run_id INTEGER,
            event_type TEXT,
            track_id INTEGER,
            timestamp_sec REAL,
            frame_number INTEGER,
            center_x REAL,
            center_y REAL
        )
        """)

        self.conn.commit()

    def save_summary(self, summary: dict):
        cur = self.conn.cursor()

        meta = summary["meta"]

        cur.execute("""
        INSERT INTO runs (source, fps, frame_width, frame_height,
                          status, total_frames, duration_sec)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            meta["source"],
            meta["fps"],
            meta["frame_width"],
            meta["frame_height"],
            meta["status"],
            meta["total_frames_processed"],
            meta["processed_duration_sec"],
        ))

        run_id = cur.lastrowid

        # Timeline
        for row in summary["timeline"]:
            cur.execute("""
            INSERT INTO timeline VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                row["timestamp_sec"],
                row["total_people"],
                row["standing"],
                row["walking"],
                row["sitting"],
                row["lying"],
                row["hand_raised"],
                row["unknown"],
            ))

        # Tracks
        for t in summary["track_summary"]:
            cur.execute("""
            INSERT INTO tracks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                t["track_id"],
                t["first_seen_sec"],
                t["last_seen_sec"],
                t["duration_sec"],
                t["frames_seen"],
                t["dominant_pose"],
                t["hand_raise_events"],
                t["avg_center_x"],
                t["avg_center_y"],
            ))

        # Events
        for e in summary["events"]:
            cur.execute("""
            INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                e["event_type"],
                e["track_id"],
                e["timestamp_sec"],
                e["frame_number"],
                e["center_x"],
                e["center_y"],
            ))

        self.conn.commit()
        return run_id