"""Live RTSP camera through OpenCV/FFmpeg. MediaMTX/WebRTC delivery is a separate path (ADR-005)."""

import threading
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit

import cv2
import numpy as np

from vision_worker.cameras.frame import Frame
from vision_worker.cameras.source import SourceUnavailableError

OPEN_TIMEOUT_MS = 5000
READ_TIMEOUT_MS = 5000


class RtspFrameSource:
    def __init__(self, url: str) -> None:
        self._url = url
        parts = urlsplit(url)
        self._label = f"rtsp:{parts.hostname}" + (f":{parts.port}" if parts.port else "")
        self._stop = threading.Event()
        self._capture: cv2.VideoCapture | None = None
        self._origin = 0.0
        self._next_frame_id = 0

    @property
    def label(self) -> str:
        return self._label

    def start(self) -> None:
        capture = cv2.VideoCapture(
            self._url,
            cv2.CAP_FFMPEG,
            [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                OPEN_TIMEOUT_MS,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                READ_TIMEOUT_MS,
            ],
        )
        if not capture.isOpened():
            capture.release()
            raise SourceUnavailableError(f"cannot connect to {self._label}")
        # Keep OpenCV's own queue minimal: freshness over completeness (§33).
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._capture = capture
        self._origin = time.monotonic()

    def read(self) -> Frame | None:
        capture = self._capture
        if capture is None or self._stop.is_set():
            return None
        ok, image = capture.read()
        if self._stop.is_set():
            return None
        if not ok or image is None:
            raise SourceUnavailableError(f"stream interrupted: {self._label}")
        self._next_frame_id += 1
        return Frame(
            image=np.asarray(image, dtype=np.uint8),  # no copy: OpenCV already gives uint8
            frame_id=self._next_frame_id,
            source_ts_ms=(time.monotonic() - self._origin) * 1000.0,
            captured_at=datetime.now(UTC),
        )

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        capture, self._capture = self._capture, None
        if capture is not None:
            capture.release()
