"""Real-time pacing for prerecorded sources so they behave like a camera (ADR-010)."""

import threading
import time
from collections.abc import Callable


class RealtimePacer:
    """Maps source time to wall time; waits are interruptible by the stop event."""

    def __init__(
        self, stop: threading.Event, monotonic: Callable[[], float] = time.monotonic
    ) -> None:
        self._stop = stop
        self._monotonic = monotonic
        self._origin: float | None = None

    def reset(self) -> None:
        self._origin = None

    def lag_ms(self, source_ts_ms: float) -> float:
        """How far wall time is ahead of the given source time (positive = we are late)."""
        if self._origin is None:
            return 0.0
        return (self._monotonic() - self._origin) * 1000.0 - source_ts_ms

    def wait_until(self, source_ts_ms: float) -> bool:
        """Sleep until the source time is due. Returns False if stop was requested."""
        now = self._monotonic()
        if self._origin is None:
            self._origin = now - source_ts_ms / 1000.0
        delay = self._origin + source_ts_ms / 1000.0 - now
        if delay > 0:
            return not self._stop.wait(delay)
        return not self._stop.is_set()
