"""Uploaded video file played at real speed in a loop (ADR-010, ADR-012)."""

import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

from vision_worker.cameras.frame import Frame
from vision_worker.cameras.pacing import RealtimePacer
from vision_worker.cameras.source import SourceFatalError

logger = logging.getLogger(__name__)

DEFAULT_FPS = 25.0


class FileFrameSource:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._stop = threading.Event()
        self._pacer = RealtimePacer(self._stop)
        self._capture: cv2.VideoCapture | None = None
        self._frame_interval_ms = 1000.0 / DEFAULT_FPS
        self._loop_offset_ms = 0.0
        self._last_pts_ms = 0.0
        self._frames_in_pass = 0
        self._next_frame_id = 0
        self._pending_discontinuity = False

    @property
    def label(self) -> str:
        return f"file:{self._path.name}"

    def start(self) -> None:
        if not self._path.is_file():
            raise SourceFatalError(f"video file not found: {self._path.name}")
        capture = cv2.VideoCapture(str(self._path))
        if not capture.isOpened():
            capture.release()
            raise SourceFatalError(f"cannot decode video file: {self._path.name}")
        fps = capture.get(cv2.CAP_PROP_FPS)
        self._frame_interval_ms = 1000.0 / fps if 0 < fps < 240 else 1000.0 / DEFAULT_FPS
        self._capture = capture
        self._pacer.reset()

    def read(self) -> Frame | None:
        capture = self._capture
        if capture is None or self._stop.is_set():
            return None
        while True:
            ok = capture.grab()
            if not ok:
                self._rewind(capture)
                continue
            pts = self._loop_offset_ms + self._position_ms(capture)
            self._frames_in_pass += 1
            self._last_pts_ms = pts
            # Behind schedule by more than a frame: skip decoding, keep real video time.
            if self._pacer.lag_ms(pts) > self._frame_interval_ms:
                continue
            if not self._pacer.wait_until(pts):
                return None
            ok, image = capture.retrieve()
            if not ok:
                continue
            discontinuity, self._pending_discontinuity = self._pending_discontinuity, False
            self._next_frame_id += 1
            return Frame(
                image=np.asarray(image, dtype=np.uint8),  # no copy: already uint8
                frame_id=self._next_frame_id,
                source_ts_ms=pts,
                captured_at=datetime.now(UTC),
                discontinuity=discontinuity,
            )

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        capture, self._capture = self._capture, None
        if capture is not None:
            capture.release()

    def _position_ms(self, capture: cv2.VideoCapture) -> float:
        # POS_MSEC after grab() is the timestamp of the grabbed frame.
        position = capture.get(cv2.CAP_PROP_POS_MSEC)
        if position <= 0 and self._frames_in_pass > 0:
            return self._frames_in_pass * self._frame_interval_ms
        return position

    def _rewind(self, capture: cv2.VideoCapture) -> None:
        if self._frames_in_pass == 0:
            raise SourceFatalError(f"video file has no frames: {self._path.name}")
        self._loop_offset_ms = self._last_pts_ms + self._frame_interval_ms
        self._frames_in_pass = 0
        self._pending_discontinuity = True
        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
        logger.debug("video file looped", extra={"source": self.label})
