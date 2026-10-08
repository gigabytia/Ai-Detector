"""Exponential reconnect backoff with an upper bound (§32)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BackoffPolicy:
    initial_seconds: float
    max_seconds: float
    factor: float = 2.0


class Backoff:
    def __init__(self, policy: BackoffPolicy) -> None:
        self._policy = policy
        self._attempts = 0

    @property
    def attempts(self) -> int:
        return self._attempts

    def next_delay(self) -> float:
        delay = self._policy.initial_seconds * self._policy.factor**self._attempts
        self._attempts += 1
        return min(delay, self._policy.max_seconds)

    def reset(self) -> None:
        self._attempts = 0
