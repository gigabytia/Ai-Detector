import threading

import numpy as np
import pytest
from worker_fakes import make_frame

from ai_detector_core.cameras.status import CameraStatus as S
from vision_worker.cameras.frame import Frame
from vision_worker.cameras.lifecycle import CameraLifecycle, InvalidTransitionError
from vision_worker.cameras.pacing import RealtimePacer
from vision_worker.cameras.reconnect import Backoff, BackoffPolicy
from vision_worker.pipeline.frame_buffer import LatestFrameBuffer


def test_backoff_grows_exponentially_up_to_max_and_resets() -> None:
    backoff = Backoff(BackoffPolicy(initial_seconds=1, max_seconds=5))
    assert [backoff.next_delay() for _ in range(5)] == [1, 2, 4, 5, 5]
    assert backoff.attempts == 5
    backoff.reset()
    assert backoff.attempts == 0
    assert backoff.next_delay() == 1


def test_latest_frame_buffer_keeps_only_newest_frame() -> None:
    buffer = LatestFrameBuffer()
    assert buffer.take() is None
    buffer.put(make_frame(1))
    buffer.put(make_frame(2))
    buffer.put(make_frame(3))
    frame = buffer.take()
    assert isinstance(frame, Frame)
    assert frame.frame_id == 3
    assert buffer.dropped == 2
    assert buffer.take() is None


def test_lifecycle_happy_path_and_reconnect() -> None:
    lifecycle = CameraLifecycle()
    for target in (S.STARTING, S.RUNNING, S.RECONNECTING, S.STARTING, S.RUNNING, S.STOPPING):
        lifecycle.transition(target)
    lifecycle.transition(S.STOPPED)
    assert lifecycle.state is S.STOPPED


@pytest.mark.parametrize(
    ("path", "target"),
    [
        ([], S.RUNNING),  # CREATED cannot skip STARTING
        ([S.STARTING, S.ERROR], S.RUNNING),  # ERROR is terminal until stopped
        ([S.STARTING, S.STOPPING, S.STOPPED], S.STARTING),  # sessions are not reused
    ],
)
def test_lifecycle_rejects_invalid_transitions(path: list[S], target: S) -> None:
    lifecycle = CameraLifecycle()
    for step in path:
        lifecycle.transition(step)
    with pytest.raises(InvalidTransitionError):
        lifecycle.transition(target)
    assert lifecycle.try_transition(target) is False


class ManualMonotonic:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_pacer_maps_source_time_to_wall_time() -> None:
    clock = ManualMonotonic()
    pacer = RealtimePacer(threading.Event(), monotonic=clock)
    assert pacer.wait_until(0.0) is True  # first frame anchors the timeline
    clock.now += 0.5
    assert pacer.lag_ms(200.0) == pytest.approx(300.0)  # 300 ms late for the 200 ms frame
    assert pacer.lag_ms(1000.0) == pytest.approx(-500.0)


def test_pacer_wait_is_interrupted_by_stop() -> None:
    stop = threading.Event()
    pacer = RealtimePacer(stop)
    assert pacer.wait_until(0.0) is True
    stop.set()
    assert pacer.wait_until(60_000.0) is False  # returns immediately instead of sleeping


def test_frame_size_is_width_height() -> None:
    frame = make_frame(1, width=32, height=16)
    assert frame.size == (32, 16)
    assert frame.image.dtype == np.uint8
