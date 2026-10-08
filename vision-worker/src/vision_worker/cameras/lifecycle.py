"""Camera lifecycle state machine with an explicit transition table (§31, §136)."""

import threading

from ai_detector_core.cameras.status import CameraStatus as S

ALLOWED_TRANSITIONS: dict[S, frozenset[S]] = {
    S.CREATED: frozenset({S.STARTING, S.STOPPING}),
    S.STARTING: frozenset({S.RUNNING, S.RECONNECTING, S.ERROR, S.STOPPING}),
    S.RUNNING: frozenset({S.DEGRADED, S.RECONNECTING, S.ERROR, S.STOPPING}),
    S.DEGRADED: frozenset({S.RUNNING, S.RECONNECTING, S.ERROR, S.STOPPING}),
    S.RECONNECTING: frozenset({S.STARTING, S.ERROR, S.STOPPING}),
    S.ERROR: frozenset({S.STOPPING}),
    S.STOPPING: frozenset({S.STOPPED}),
    S.STOPPED: frozenset(),
}


class InvalidTransitionError(RuntimeError):
    pass


class CameraLifecycle:
    """Thread-safe: the capture thread and the asyncio side both move the state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = S.CREATED

    @property
    def state(self) -> S:
        with self._lock:
            return self._state

    def transition(self, target: S) -> None:
        with self._lock:
            if target not in ALLOWED_TRANSITIONS[self._state]:
                raise InvalidTransitionError(f"{self._state} -> {target}")
            self._state = target

    def try_transition(self, target: S) -> bool:
        """Transition if allowed; used where a concurrent stop may have won the race."""
        with self._lock:
            if target not in ALLOWED_TRANSITIONS[self._state]:
                return False
            self._state = target
            return True
