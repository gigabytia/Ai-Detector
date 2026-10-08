"""Wall-clock abstraction so time-based logic can be tested with fixed time."""

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
