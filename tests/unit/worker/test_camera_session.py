import time
import uuid
from collections.abc import Callable, Iterator

import pytest
from worker_fakes import ScriptedSource, make_frame

from ai_detector_core.cameras.source import SourceType
from ai_detector_core.cameras.spec import CameraSpec
from ai_detector_core.cameras.status import CameraStatus
from fakes import FixedClock
from vision_worker.cameras.reconnect import BackoffPolicy
from vision_worker.cameras.session import CameraSession
from vision_worker.cameras.source import SourceFatalError, SourceUnavailableError

SPEC = CameraSpec(
    id=uuid.uuid4(),
    name="Тест",
    source_type=SourceType.RTSP,
    source_url="rtsp://cam.local/s",
    enabled=True,
)
SessionFactory = Callable[[ScriptedSource], CameraSession]
FAST = BackoffPolicy(initial_seconds=0.01, max_seconds=0.02)


def wait_for(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached in time")
        time.sleep(0.005)


@pytest.fixture
def make_session() -> Iterator[SessionFactory]:
    sessions: list[CameraSession] = []

    def factory(source: ScriptedSource) -> CameraSession:
        session = CameraSession(SPEC, source, FAST, "worker-test", FixedClock())
        sessions.append(session)
        return session

    yield factory
    for session in sessions:
        session.stop()


def test_first_frame_moves_session_to_running(make_session: SessionFactory) -> None:
    source = ScriptedSource()
    session = make_session(source)
    session.start()
    assert session.state is CameraStatus.STARTING
    source.items.put(make_frame(1, width=640, height=360))
    wait_for(lambda: session.state is CameraStatus.RUNNING)
    wait_for(lambda: session.status().frame_size == (640, 360))
    status = session.status()
    assert status.worker_id == "worker-test"
    assert status.run_id == session.run_id
    assert status.last_frame_at is not None
    assert session.buffer.take() is not None


def test_unavailable_source_reconnects_and_recovers(make_session: SessionFactory) -> None:
    source = ScriptedSource(
        start_errors=[SourceUnavailableError("down"), SourceUnavailableError("down")]
    )
    session = make_session(source)
    session.start()
    wait_for(lambda: source.starts == 3)
    source.items.put(make_frame(1))
    wait_for(lambda: session.state is CameraStatus.RUNNING)
    status = session.status()
    assert status.reconnect_attempts == 0  # reset after the first good frame
    assert status.last_reconnect_attempt_at is not None
    assert status.last_error is None


def test_stream_interruption_goes_through_reconnecting(make_session: SessionFactory) -> None:
    source = ScriptedSource()
    session = CameraSession(
        SPEC, source, BackoffPolicy(initial_seconds=0.3, max_seconds=0.3), "w", FixedClock()
    )
    session.start()
    source.items.put(make_frame(1))
    wait_for(lambda: session.state is CameraStatus.RUNNING)
    source.items.put(SourceUnavailableError("stream interrupted"))
    wait_for(lambda: session.state is CameraStatus.RECONNECTING)
    assert session.status().last_error == "stream interrupted"
    assert session.status().reconnect_attempts == 1
    session.stop()
    assert session.state is CameraStatus.STOPPED


def test_fatal_error_stops_in_error_state_without_retries(make_session: SessionFactory) -> None:
    source = ScriptedSource(start_errors=[SourceFatalError("video file not found: x.mp4")])
    session = make_session(source)
    session.start()
    wait_for(lambda: session.state is CameraStatus.ERROR)
    time.sleep(0.05)
    assert source.starts == 1
    assert session.status().last_error == "video file not found: x.mp4"
    assert source.closes >= 1


def test_stop_releases_source_and_is_final(make_session: SessionFactory) -> None:
    source = ScriptedSource()
    session = make_session(source)
    session.start()
    source.items.put(make_frame(1))
    wait_for(lambda: session.state is CameraStatus.RUNNING)
    session.stop()
    assert session.state is CameraStatus.STOPPED
    assert source.closes >= 1
    session.stop()  # idempotent
    assert session.state is CameraStatus.STOPPED


def test_unexpected_exception_is_reported_as_error(make_session: SessionFactory) -> None:
    source = ScriptedSource(start_errors=[RuntimeError("bug")])
    session = make_session(source)
    session.start()
    wait_for(lambda: session.state is CameraStatus.ERROR)
    assert session.status().last_error == "bug"
