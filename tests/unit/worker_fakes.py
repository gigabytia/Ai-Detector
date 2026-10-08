"""Fakes for vision-worker unit tests."""

import queue
import threading
from datetime import UTC, datetime

import numpy as np

from vision_worker.cameras.frame import Frame


def make_frame(frame_id: int, width: int = 8, height: int = 6) -> Frame:
    return Frame(
        image=np.zeros((height, width, 3), dtype=np.uint8),
        frame_id=frame_id,
        source_ts_ms=frame_id * 40.0,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class ScriptedSource:
    """FrameSource whose behaviour is fed by the test: frames or errors, one per read()."""

    label = "fake:scripted"

    def __init__(self, start_errors: list[Exception] | None = None) -> None:
        self.start_errors = list(start_errors or [])
        self.items: queue.Queue[Frame | Exception] = queue.Queue()
        self.starts = 0
        self.closes = 0
        self._stop = threading.Event()

    def start(self) -> None:
        self.starts += 1
        if self.start_errors:
            raise self.start_errors.pop(0)

    def read(self) -> Frame | None:
        while not self._stop.is_set():
            try:
                item = self.items.get(timeout=0.01)
            except queue.Empty:
                continue
            if isinstance(item, Exception):
                raise item
            return item
        return None

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        self.closes += 1
