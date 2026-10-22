"""Bounded metrics, monotonic latency and no-impossible-batch-wait regressions."""

import asyncio
import time
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import replace
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families
from redis.asyncio import Redis
from worker_fakes import ScriptedSource, make_frame

from ai_detector_core.cameras.spec import CameraSpec
from ai_detector_core.cameras.status import CameraStatus
from ai_detector_core.events.domain import DomainEvent
from fakes import FixedClock
from vision_worker.cameras.frame import Frame
from vision_worker.cameras.manager import CameraManager
from vision_worker.cameras.reconnect import BackoffPolicy
from vision_worker.cameras.session import CameraSession
from vision_worker.http.app import create_http_app
from vision_worker.inference.detector import PersonDetection
from vision_worker.messaging.events import EventPublisher
from vision_worker.pipeline.frame_buffer import LatestFrameBuffer
from vision_worker.pipeline.metrics import PipelineMetrics
from vision_worker.pipeline.preview import PreviewHub
from vision_worker.pipeline.results import DetectionResult
from vision_worker.pipeline.scheduler import InferenceScheduler, WorkItem
from vision_worker.supervisor import Supervisor


@pytest.fixture
def sessions() -> Iterator[list[CameraSession]]:
    values: list[CameraSession] = []
    yield values
    for session in values:
        session.stop()


def session(values: list[CameraSession]) -> CameraSession:
    spec = CameraSpec(
        id=uuid.uuid4(),
        name="private camera",
        source_type="rtsp",
        source_url="rtsp://private:secret@camera.local/stream",
        enabled=True,
    )
    result = CameraSession(spec, ScriptedSource(), BackoffPolicy(1, 30), "test", FixedClock())
    result._lifecycle.transition(CameraStatus.STARTING)
    result._lifecycle.transition(CameraStatus.RUNNING)
    values.append(result)
    return result


def sample(metrics: PipelineMetrics, name: str, **labels: str) -> float | None:
    return metrics.registry.get_sample_value(name, labels)


def sup(metrics: PipelineMetrics, values: list[CameraSession]) -> Supervisor:
    return cast(
        Supervisor,
        SimpleNamespace(
            manager=SimpleNamespace(sessions=values),
            events=None,
            analytics=None,
            heartbeat=SimpleNamespace(redis_ok=True),
            detector_info={"device": "cpu"},
            scheduler=SimpleNamespace(metrics=metrics),
        ),
    )


class Detector:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def detect(self, frames: Sequence[Frame], confidence: float) -> list[list[PersonDetection]]:
        if self.fail:
            raise RuntimeError("failed test detector")
        return [[] for _ in frames]


def test_buffer_depth_is_bounded_and_separate_from_replacements() -> None:
    buffer = LatestFrameBuffer()
    assert buffer.depth == 0
    for i in range(10):
        buffer.put(make_frame(i))
        assert buffer.depth == 1
    assert buffer.dropped == 9
    frame = buffer.take()
    assert frame is not None and frame.frame_id == 9
    assert buffer.depth == 0 and buffer.dropped == 9


def test_latency_uses_handoff_monotonic_not_source_or_wall(
    sessions: list[CameraSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = session(sessions)
    assert value.performance().result_age_seconds is None
    now = [100.0]
    monkeypatch.setattr("vision_worker.cameras.session.time.monotonic", lambda: now[0])
    frame = replace(make_frame(1), source_ts_ms=-1_000_000, captured_monotonic=99.75)
    value.record_result(DetectionResult(value.camera_id, value.run_id, frame, (), 12))
    perf = value.performance()
    assert perf.local_latency_seconds == 0.25 and perf.processed_frames == 1
    now[0] = 101.5
    assert value.performance().result_age_seconds == 1.5
    # Direct/legacy frames without handoff clock are unavailable, not synthetic zero.
    value.record_result(DetectionResult(value.camera_id, value.run_id, make_frame(2), (), 0))
    assert value.performance().local_latency_seconds is None


def test_metrics_remove_camera_and_new_run_stale_values(sessions: list[CameraSession]) -> None:
    value = session(sessions)
    frame = replace(make_frame(1), captured_monotonic=time.monotonic() - 0.1)
    value.record_result(DetectionResult(value.camera_id, value.run_id, frame, (), 0))
    metrics = PipelineMetrics()
    supervisor = sup(metrics, [value])
    metrics.render(supervisor)
    labels = {"camera_id": str(value.camera_id)}
    assert sample(metrics, "ai_detector_camera_local_latency_seconds", **labels) is not None
    # Restart with the same ID, but no result yet.
    replacement = session(sessions)
    replacement.spec = replacement.spec.model_copy(update={"id": value.camera_id})
    supervisor.manager.sessions[:] = [replacement]
    metrics.render(supervisor)
    assert sample(metrics, "ai_detector_camera_local_latency_seconds", **labels) is None
    assert sample(metrics, "ai_detector_camera_processed_frames", **labels) == 0
    supervisor.manager.sessions.clear()
    metrics.render(supervisor)
    metrics.render(supervisor)
    assert not metrics._camera_ids
    assert sample(metrics, "ai_detector_camera_capture_fps", **labels) is None


def test_metrics_stop_before_first_result_and_no_sensitive_labels(
    sessions: list[CameraSession],
) -> None:
    value = session(sessions)
    metrics = PipelineMetrics()
    supervisor = sup(metrics, [value])
    body = metrics.render(supervisor).decode()
    assert "secret" not in body and "private camera" not in body and "camera.local" not in body
    supervisor.manager.sessions.clear()
    metrics.render(supervisor)  # no KeyError for absent result-age/latency child
    assert not metrics._camera_ids


def test_metrics_histogram_cumulative_buckets_and_isolated_registries() -> None:
    first, second = PipelineMetrics(), PipelineMetrics()
    for value in [0.005, 0.1, 20]:
        first.local_latency.observe(value)
    assert sample(first, "ai_detector_local_frame_latency_seconds_count") == 3
    assert sample(first, "ai_detector_local_frame_latency_seconds_bucket", le="0.1") == 2
    assert sample(first, "ai_detector_local_frame_latency_seconds_bucket", le="+Inf") == 3
    assert sample(second, "ai_detector_local_frame_latency_seconds_count") == 0


def test_metrics_http_is_prometheus_without_external_io(sessions: list[CameraSession]) -> None:
    value = session(sessions)
    metrics = PipelineMetrics()
    supervisor = sup(metrics, [value])
    publisher = EventPublisher(cast(Redis, object()), capacity=2)
    publisher.dropped = 2
    publisher.healthy = False
    publisher.queue.put_nowait(cast(DomainEvent, object()))
    supervisor.events = publisher
    response = TestClient(create_http_app(supervisor)).get("/metrics")
    assert response.status_code == 200 and "text/plain" in response.headers["content-type"]
    assert response.headers["cache-control"] == "no-store"
    assert list(text_string_to_metric_families(response.text))
    assert sample(metrics, "ai_detector_outbox_queue_depth", kind="events") == 1
    assert sample(metrics, "ai_detector_outbox_dropped", kind="events") == 2
    assert sample(metrics, "ai_detector_delivery_healthy", kind="events") == 0
    assert sample(metrics, "ai_detector_cuda_enabled") == 0


async def test_batch_fills_only_from_other_running_cameras(sessions: list[CameraSession]) -> None:
    first, second = session(sessions), session(sessions)
    manager = CameraManager(lambda _: first)
    manager._sessions = {s.camera_id: s for s in [first, second]}
    hub = PreviewHub()
    scheduler = InferenceScheduler(manager, Detector(), hub)
    item = WorkItem(first, make_frame(1), 0.25)
    try:
        assert scheduler.can_fill_batch([item])
        second._lifecycle.try_transition(CameraStatus.RECONNECTING)
        assert not scheduler.can_fill_batch([item])
        second._lifecycle.try_transition(CameraStatus.STARTING)
        assert not scheduler.can_fill_batch([item])
        second._lifecycle.try_transition(CameraStatus.RUNNING)
        assert scheduler.can_fill_batch([item])
        assert not scheduler.can_fill_batch([item, WorkItem(second, make_frame(1), 0.25)])
    finally:
        scheduler._pool.shutdown()
        await hub.close()


@pytest.mark.parametrize("fail", [False, True])
async def test_single_camera_never_waits_for_impossible_batch(
    sessions: list[CameraSession],
    fail: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = session(sessions)
    value.buffer.put(replace(make_frame(1), captured_monotonic=time.monotonic()))
    manager = CameraManager(lambda _: value)
    manager._sessions[value.camera_id] = value
    hub = PreviewHub()
    scheduler = InferenceScheduler(manager, Detector(fail), hub, max_wait_ms=5000)
    stop = asyncio.Event()
    delivered = asyncio.Event()
    original_result, original_error = value.record_result, value.record_inference_error

    def result_received(result: DetectionResult) -> None:
        original_result(result)
        delivered.set()

    def error_received(error: Exception) -> None:
        original_error(error)
        delivered.set()

    monkeypatch.setattr(value, "record_result", result_received)
    monkeypatch.setattr(value, "record_inference_error", error_received)
    task = asyncio.create_task(scheduler.run(stop))
    try:
        await asyncio.wait_for(delivered.wait(), 2)
        name = "ai_detector_pipeline_errors_total" if fail else "ai_detector_processed_frames_total"
        assert sample(scheduler.metrics, name) == 1
        assert sample(scheduler.metrics, "ai_detector_detector_batch_size_sum", kind="real") == 1
        assert (
            sample(scheduler.metrics, "ai_detector_detector_call_seconds_count", kind="real") == 1
        )
        if not fail:
            assert sample(scheduler.metrics, "ai_detector_local_frame_latency_seconds_count") == 1
    finally:
        stop.set()
        await asyncio.wait_for(task, 2)
        assert sample(scheduler.metrics, "ai_detector_inflight_frames") == 0
        await hub.close()


@pytest.mark.parametrize("threads", [1, 2, 8])
def test_adapter_restores_explicit_threads_after_predictor_warmup(
    monkeypatch: pytest.MonkeyPatch,
    threads: int,
) -> None:
    from pathlib import Path

    import torch

    from vision_worker.inference.adapters import ultralytics as adapter
    from vision_worker.inference.manifest import ModelManifest

    current = [0]
    calls: list[int] = []

    def set_threads(value: int) -> None:
        current[0] = value
        calls.append(value)

    def warmup(
        self: adapter.UltralyticsPersonDetector, frames: Sequence[Frame], confidence: float
    ) -> list[list[PersonDetection]]:
        set_threads(1)  # simulate Ultralytics select_device CPU setup
        return [[] for _ in frames]

    manifest = ModelManifest(
        name="test",
        backend="ultralytics",
        weights="test.pt",
        sha256="0" * 64,
        download_url="https://example.com/test.pt",
        input_size=32,
        person_class_id=0,
        license="test",
    )
    monkeypatch.setattr(adapter, "read_manifest", lambda _: manifest)
    monkeypatch.setattr(adapter, "verify_weights", lambda *_: Path("test.pt"))
    monkeypatch.setattr(adapter, "YOLO", lambda _: SimpleNamespace(names={0: "person"}))
    monkeypatch.setattr(torch, "set_num_threads", set_threads)
    monkeypatch.setattr(torch, "get_num_threads", lambda: current[0])
    monkeypatch.setattr(adapter.UltralyticsPersonDetector, "detect", warmup)
    value = adapter.UltralyticsPersonDetector(Path("manifest.yaml"), "cpu", 0.45, threads)
    assert calls == [threads, 1, threads] and value.threads == threads


async def test_stop_during_batch_wait_resets_inflight(
    sessions: list[CameraSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = session(sessions), session(sessions)
    first.buffer.put(make_frame(1))
    manager = CameraManager(lambda _: first)
    manager._sessions = {s.camera_id: s for s in [first, second]}
    hub = PreviewHub()
    scheduler = InferenceScheduler(manager, Detector(), hub, max_wait_ms=5000)
    stop = asyncio.Event()
    selected = asyncio.Event()
    original_set = scheduler.metrics.inflight.set

    def inflight_set(value: float) -> None:
        original_set(value)
        if value == 1:
            selected.set()

    monkeypatch.setattr(scheduler.metrics.inflight, "set", inflight_set)
    task = asyncio.create_task(scheduler.run(stop))
    try:
        await asyncio.wait_for(selected.wait(), 2)
        stop.set()
        await asyncio.wait_for(task, 2)
        assert sample(scheduler.metrics, "ai_detector_inflight_frames") == 0
        assert sample(scheduler.metrics, "ai_detector_processed_frames_total") == 0
    finally:
        stop.set()
        await asyncio.wait_for(task, 2)
        await hub.close()
