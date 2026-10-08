"""Latest-frame buffer between a capture thread and its consumer (§33: freshness > completeness)."""

import threading

from vision_worker.cameras.frame import Frame


class LatestFrameBuffer:
    """Holds at most one frame; a new frame replaces an unconsumed one and counts as dropped."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: Frame | None = None
        self._dropped = 0

    def put(self, frame: Frame) -> None:
        with self._lock:
            if self._frame is not None:
                self._dropped += 1
            self._frame = frame

    def take(self) -> Frame | None:
        with self._lock:
            frame, self._frame = self._frame, None
            return frame

    @property
    def dropped(self) -> int:
        with self._lock:
            return self._dropped
