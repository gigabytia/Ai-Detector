"""Deterministic inference/preview contracts: no weights/network/GPU needed."""

import asyncio
import hashlib
import json
import struct
import time
import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path

import cv2
import numpy as np
import pytest
from worker_fakes import ScriptedSource, make_frame

from ai_detector_core.cameras.config import CameraConfig
from ai_detector_core.cameras.source import SourceType
from ai_detector_core.cameras.spec import CameraSpec
from ai_detector_core.cameras.status import CameraStatus
from fakes import FixedClock
from vision_worker.cameras.frame import Frame
from vision_worker.cameras.manager import CameraManager
from vision_worker.cameras.reconnect import BackoffPolicy
from vision_worker.cameras.scenario import load_scenario
from vision_worker.cameras.session import CameraSession
from vision_worker.inference.adapters.scripted import ScriptedPersonDetector
from vision_worker.inference.detector import PersonDetection
from vision_worker.inference.manifest import ModelManifest, verify_weights, weights_path
from vision_worker.pipeline.preview import PreviewHub, encode_packet
from vision_worker.pipeline.results import DetectionResult
from vision_worker.pipeline.scheduler import InferenceScheduler, WorkItem


class FakeDetector:
    def __init__(self) -> None:
        self.calls: list[tuple[int, float]] = []
        self.error = False

    def detect(self, frames: Sequence[Frame], confidence: float) -> list[list[PersonDetection]]:
        self.calls.append((len(frames), confidence))
        if self.error:
            raise RuntimeError("test inference failed")
        return [
            [PersonDetection((1, 1, 6, 5), 0.9), PersonDetection((2, 1, 5, 4), 0.4)] for _ in frames
        ]


@pytest.fixture
def sessions() -> Iterator[list[CameraSession]]:
    values: list[CameraSession] = []
    yield values
    for session in values:
        session.stop()


def make_session(
    sessions: list[CameraSession], *, mock: bool = False, confidence: float = 0.25
) -> CameraSession:
    source = ScriptedSource()
    spec = CameraSpec(
        id=uuid.uuid4(),
        name="test",
        source_type=SourceType.MOCK if mock else SourceType.RTSP,
        source_url="mock://two_people" if mock else "rtsp://cam.local/s",
        enabled=True,
        config=CameraConfig(target_fps=30, detection_confidence=confidence),
    )
    session = CameraSession(
        spec, source, BackoffPolicy(initial_seconds=1, max_seconds=30), "test", FixedClock()
    )
    sessions.append(session)
    session.start()
    source.items.put(make_frame(1))
    deadline = time.monotonic() + 2
    while session.status().frame_size is None:
        assert time.monotonic() < deadline
        time.sleep(0.002)
    return session


def result(frame_id: int = 1) -> DetectionResult:
    return DetectionResult(
        uuid.uuid4(),
        uuid.uuid4(),
        make_frame(frame_id, 1280, 720),
        (PersonDetection((128, 72, 640, 648), 0.9),),
        12.5,
    )


def test_scripted_uses_source_time_and_pixel_coordinates() -> None:
    scenario = load_scenario("two_people")
    frame = make_frame(50, scenario.width, scenario.height)
    detections = ScriptedPersonDetector(scenario).detect([frame], 0.25)[0]
    expected = scenario.boxes_at(frame.source_ts_ms / 1000)
    assert len(detections) == len(expected) > 0
    for detection, (_, box) in zip(detections, expected, strict=True):
        assert detection.bbox == pytest.approx(
            (
                box[0] * scenario.width,
                box[1] * scenario.height,
                box[2] * scenario.width,
                box[3] * scenario.height,
            )
        )


def test_packet_is_atomic_and_boxes_are_normalized() -> None:
    value = result()
    packet = encode_packet(value, 640)
    (length,) = struct.unpack("!I", packet[:4])
    header = json.loads(packet[4 : 4 + length])
    image = cv2.imdecode(np.frombuffer(packet[4 + length :], dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    assert image.shape[:2] == (360, 640)
    assert header["camera_id"] == str(value.camera_id)
    assert header["run_id"] == str(value.run_id)
    assert header["frame_id"] == value.frame.frame_id
    assert header["detections"][0]["bbox"] == pytest.approx([0.1, 0.1, 0.5, 0.9])
    assert header["inference_ms"] == 12.5


def test_encode_does_not_upscale_small_images() -> None:
    value = DetectionResult(uuid.uuid4(), uuid.uuid4(), make_frame(1), (), 0)
    packet = encode_packet(value, 640)
    (length,) = struct.unpack("!I", packet[:4])
    image = cv2.imdecode(np.frombuffer(packet[4 + length :], dtype=np.uint8), 1)
    assert image is not None and image.shape[:2] == (6, 8)


async def test_preview_is_on_demand_and_latest_only() -> None:
    hub = PreviewHub(fps=30)
    value = result()
    try:
        hub.offer(value)
        assert not hub._tasks
        first = hub.subscribe(value.camera_id)
        second = hub.subscribe(value.camera_id)
        hub.offer(value)
        await asyncio.sleep(0.1)
        assert first.qsize() == second.qsize() == 1
        next_result = DetectionResult(value.camera_id, value.run_id, make_frame(2), (), 0)
        hub.offer(next_result)
        await asyncio.sleep(0.1)
        assert first.qsize() == 1
        packet = first.get_nowait()
        (size,) = struct.unpack("!I", packet[:4])
        assert json.loads(packet[4 : 4 + size])["frame_id"] == 2
        hub.unsubscribe(value.camera_id, first)
        hub.unsubscribe(value.camera_id, second)
        assert not hub._viewers
    finally:
        await hub.close()


async def test_batch_keeps_per_camera_thresholds_and_mock_independence(
    sessions: list[CameraSession],
) -> None:
    low = make_session(sessions, confidence=0.25)
    high = make_session(sessions, confidence=0.8)
    mock = make_session(sessions, mock=True)
    detector = FakeDetector()
    hub = PreviewHub()
    scheduler = InferenceScheduler(CameraManager(lambda _: low), detector, hub)
    items = [
        WorkItem(s, make_frame(50), s.spec.config.detection_confidence) for s in [low, high, mock]
    ]
    try:
        output = scheduler._infer(items)
        assert detector.calls == [(2, 0.25)]
        a, b, c = output
        assert isinstance(a, DetectionResult) and len(a.detections) == 2
        assert isinstance(b, DetectionResult) and len(b.detections) == 1
        assert isinstance(c, DetectionResult) and len(c.detections) > 0
        detector.error = True
        output = scheduler._infer(items)
        assert isinstance(output[0], RuntimeError)
        assert isinstance(output[1], RuntimeError)
        assert isinstance(output[2], DetectionResult)
    finally:
        scheduler._pool.shutdown()
        await hub.close()


async def test_scheduler_is_fair_and_respects_target_fps(sessions: list[CameraSession]) -> None:
    pool = [make_session(sessions) for _ in range(8)]
    by_id = {s.camera_id: s for s in pool}
    manager = CameraManager(lambda spec: by_id[spec.id])
    for s in pool:
        manager._sessions[s.camera_id] = s
    hub = PreviewHub()
    scheduler = InferenceScheduler(manager, FakeDetector(), hub)
    try:
        first = scheduler.collect(4)
        second = scheduler.collect(4)
        assert {i.session.camera_id for i in first + second} == set(by_id)
        for s in pool:
            s.buffer.put(make_frame(2))
        assert scheduler.collect(8) == []
        await asyncio.sleep(0.04)
        assert len(scheduler.collect(8)) == 8
    finally:
        scheduler._pool.shutdown()
        await hub.close()
        await manager.stop_all()


async def test_hot_config_update_keeps_run_and_source(sessions: list[CameraSession]) -> None:
    session = make_session(sessions)
    manager = CameraManager(lambda _: session)
    manager._sessions[session.camera_id] = session
    run = session.run_id
    await manager.apply(
        session.camera_id, session.spec.model_copy(update={"config": CameraConfig(target_fps=3)})
    )
    assert session.run_id == run
    assert session.state == CameraStatus.RUNNING
    assert session.spec.config.target_fps == 3


async def test_scheduler_processes_and_stops_cleanly(sessions: list[CameraSession]) -> None:
    session = make_session(sessions)
    manager = CameraManager(lambda _: session)
    manager._sessions[session.camera_id] = session
    hub = PreviewHub()
    queue = hub.subscribe(session.camera_id)
    detector = FakeDetector()
    scheduler = InferenceScheduler(manager, detector, hub, max_wait_ms=0)
    stop = asyncio.Event()
    task = asyncio.create_task(scheduler.run(stop))
    try:
        await asyncio.wait_for(queue.get(), 2)
        assert session.status().detections_count == 2
        assert session.status().inference_ms is not None
    finally:
        stop.set()
        await asyncio.wait_for(task, 2)
        await hub.close()
        await manager.stop_all()


def test_inference_error_is_not_cleared_by_capture(sessions: list[CameraSession]) -> None:
    session = make_session(sessions)
    session.record_inference_error(RuntimeError("broken"))
    session.buffer.put(make_frame(2))
    assert session.state == CameraStatus.DEGRADED
    assert session.status().inference_error == "broken"
    session.record_result(DetectionResult(session.camera_id, session.run_id, make_frame(3), (), 0))
    assert session.status().inference_error is None
    assert session.status().status == CameraStatus.RUNNING


def manifest(digest: str, weights: str = "model.pt") -> ModelManifest:
    return ModelManifest(
        name="test",
        backend="ultralytics",
        weights=weights,
        sha256=digest,
        download_url="https://example.com/model.pt",
        input_size=640,
        person_class_id=0,
        license="AGPL-3.0",
    )


def test_model_integrity_and_missing_weights(tmp_path: Path) -> None:
    path = tmp_path / "manifest.yaml"
    weights = tmp_path / "model.pt"
    weights.write_bytes(b"test")
    good = manifest(hashlib.sha256(b"test").hexdigest())
    assert verify_weights(path, good) == weights
    with pytest.raises(ValueError, match="sha256"):
        verify_weights(path, manifest("0" * 64))
    weights.unlink()
    with pytest.raises(FileNotFoundError):
        verify_weights(path, good)
    with pytest.raises(ValueError, match="inside"):
        weights_path(path, manifest("0" * 64, "../escape.pt"))


def test_degraded_threshold_and_recovery(
    sessions: list[CameraSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    session = make_session(sessions)
    now = [100.0]
    monkeypatch.setattr("vision_worker.cameras.session.time.monotonic", lambda: now[0])
    monkeypatch.setattr(session._rate, "rate", lambda: 5.0)
    monkeypatch.setattr(session._processed_rate, "rate", lambda: 2.0)
    session.check_performance()
    assert session.status().status == CameraStatus.RUNNING
    now[0] = 106
    session.check_performance()
    assert session.status().status == CameraStatus.DEGRADED
    # Source-limited 5 FPS is healthy even with a 30 FPS target.
    monkeypatch.setattr(session._processed_rate, "rate", lambda: 4.5)
    session.check_performance()
    assert session.status().status == CameraStatus.RUNNING


async def test_completed_result_from_stopped_run_is_discarded(
    sessions: list[CameraSession],
) -> None:
    import threading

    started, release = threading.Event(), threading.Event()

    class BlockingDetector(FakeDetector):
        def detect(self, frames: Sequence[Frame], confidence: float) -> list[list[PersonDetection]]:
            started.set()
            assert release.wait(timeout=3)
            return super().detect(frames, confidence)

    session = make_session(sessions)
    manager = CameraManager(lambda _: session)
    manager._sessions[session.camera_id] = session
    hub = PreviewHub()
    queue = hub.subscribe(session.camera_id)
    scheduler = InferenceScheduler(manager, BlockingDetector(), hub, max_wait_ms=0)
    stop = asyncio.Event()
    task = asyncio.create_task(scheduler.run(stop))
    try:
        deadline = time.monotonic() + 2
        while not started.is_set():
            assert time.monotonic() < deadline
            await asyncio.sleep(0.005)
        await manager.stop_all()
        release.set()
        stop.set()
        await asyncio.wait_for(task, 2)
        assert queue.empty()
        assert session.status().detections_count == 0
    finally:
        release.set()
        stop.set()
        await asyncio.gather(task, return_exceptions=True)
        await hub.close()


async def test_scripted_success_does_not_mask_repeated_model_failure(
    sessions: list[CameraSession],
) -> None:
    real = make_session(sessions)
    mock = make_session(sessions, mock=True)
    hub = PreviewHub()
    detector = FakeDetector()
    scheduler = InferenceScheduler(CameraManager(lambda _: real), detector, hub)
    items = [WorkItem(s, make_frame(50), 0.25) for s in [real, mock]]
    try:
        detector.error = True
        for _ in range(3):
            scheduler._record_batch_health(items, scheduler._infer(items))
        assert not scheduler.healthy
        detector.error = False
        scheduler._record_batch_health(items, scheduler._infer(items))
        assert scheduler.healthy
    finally:
        scheduler._pool.shutdown()
        await hub.close()
