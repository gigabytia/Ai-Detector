"""Capture rate over a sliding window."""

import time
from collections import deque
from collections.abc import Callable

WINDOW_SECONDS = 2.0


class RateMeter:
    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._monotonic = monotonic
        self._ticks: deque[float] = deque(maxlen=256)

    def tick(self) -> None:
        self._ticks.append(self._monotonic())

    def rate(self) -> float:
        now = self._monotonic()
        recent = [t for t in self._ticks if now - t <= WINDOW_SECONDS]
        if len(recent) < 2:
            return 0.0
        span = recent[-1] - recent[0]
        return (len(recent) - 1) / span if span > 0 else 0.0
