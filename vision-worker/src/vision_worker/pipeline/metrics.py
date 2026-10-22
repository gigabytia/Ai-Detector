"""Worker-local, bounded-label Prometheus metrics; scrapes never query external stores."""

from contextlib import suppress
from typing import TYPE_CHECKING

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    ProcessCollector,
    generate_latest,
)

from vision_worker.cameras.session import CameraSession

if TYPE_CHECKING:
    from vision_worker.supervisor import Supervisor

SECONDS_BUCKETS = (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10)


class PipelineMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.detector_info = Info(
            "ai_detector_detector", "Loaded detector configuration", registry=self.registry
        )
        # Standard process CPU-seconds/RSS/open-fd collectors where supported by the OS.
        ProcessCollector(registry=self.registry)
        self.processed = Counter(
            "ai_detector_processed_frames",
            "Successfully delivered local pipeline results",
            registry=self.registry,
        )
        self.errors = Counter(
            "ai_detector_pipeline_errors", "Failed frame results", registry=self.registry
        )
        self.stale = Counter(
            "ai_detector_stale_results",
            "Obsolete results discarded after stop/restart",
            registry=self.registry,
        )
        self.events = Counter(
            "ai_detector_generated_events",
            "Rule alarms generated, not persistence acknowledgements",
            ["type"],
            registry=self.registry,
        )
        self.local_latency = Histogram(
            "ai_detector_local_frame_latency_seconds",
            "Capture handoff to result delivery; excludes sensor/network/decode and persistence/UI",
            buckets=SECONDS_BUCKETS,
            registry=self.registry,
        )
        self.detector_call = Histogram(
            "ai_detector_detector_call_seconds",
            "Whole detector call wall duration; not amortized per frame",
            ["kind"],
            buckets=SECONDS_BUCKETS,
            registry=self.registry,
        )
        self.batch_size = Histogram(
            "ai_detector_detector_batch_size",
            "Frames in a detector call",
            ["kind"],
            buckets=(1, 2, 4, 8, 16, 32),
            registry=self.registry,
        )
        self.batch_wait = Histogram(
            "ai_detector_batch_wait_seconds",
            "First selected frame to executor submission",
            buckets=SECONDS_BUCKETS,
            registry=self.registry,
        )
        self.inflight = Gauge(
            "ai_detector_inflight_frames",
            "Selected frames including batch wait and inference",
            registry=self.registry,
        )
        self.camera = {
            name: Gauge(
                "ai_detector_camera_" + name, help_text, ["camera_id"], registry=self.registry
            )
            for name, help_text in {
                "capture_fps": "Sliding two-second capture FPS",
                "processed_fps": "Sliding two-second processed FPS",
                "capture_queue_depth": "Pending capture frames (0/1), excludes in-flight batch",
                "dropped_frames": "Capture replacements since camera run start; resets on restart",
                "processed_frames": "Successful results since camera run start; resets on restart",
                "active_tracks": "Non-LOST tracks in last result; inspect result age",
                "result_age_seconds": "Age of last successful result; absent before first result",
                "local_latency_seconds": "Last handoff latency; absent until first result",
                "reconnect_attempts": "Current backoff attempts, resets on successful connection",
            }.items()
        }
        self._camera_ids: set[str] = set()
        self.queues = Gauge(
            "ai_detector_outbox_queue_depth",
            "Waiting RAM records only, excludes pending delivery and Redis Streams",
            ["kind"],
            registry=self.registry,
        )
        self.dropped = Gauge(
            "ai_detector_outbox_dropped",
            "RAM records dropped since worker startup",
            ["kind"],
            registry=self.registry,
        )
        self.delivery_healthy = Gauge(
            "ai_detector_delivery_healthy",
            "Local publisher health, not end-to-end durability",
            ["kind"],
            registry=self.registry,
        )
        self.redis_healthy = Gauge(
            "ai_detector_redis_healthy",
            "Last heartbeat Redis result; scrape does no network I/O",
            registry=self.registry,
        )
        self.cuda_enabled = Gauge(
            "ai_detector_cuda_enabled",
            "Detector configured for CUDA; not utilization or availability probe",
            registry=self.registry,
        )

    def render(self, supervisor: "Supervisor") -> bytes:
        sessions = [s for s in supervisor.manager.sessions if isinstance(s, CameraSession)]
        current = {str(s.camera_id) for s in sessions}
        for camera_id in self._camera_ids - current:
            for gauge in self.camera.values():
                with suppress(KeyError):
                    gauge.remove(camera_id)
        self._camera_ids = current
        for session in sessions:
            camera_id = str(session.camera_id)
            status, perf = session.status(), session.performance()
            values = {
                "capture_fps": status.capture_fps,
                "processed_fps": status.processed_fps,
                "capture_queue_depth": session.buffer.depth,
                "dropped_frames": status.dropped_frames,
                "processed_frames": perf.processed_frames,
                "active_tracks": perf.active_tracks,
                "result_age_seconds": perf.result_age_seconds,
                "local_latency_seconds": perf.local_latency_seconds,
                "reconnect_attempts": status.reconnect_attempts,
            }
            for name, value in values.items():
                gauge = self.camera[name]
                if value is not None:
                    gauge.labels(camera_id).set(value)
                elif camera_id in self._camera_ids:
                    # Existing ID can acquire a new run with no result yet. Remove stale values.
                    with suppress(KeyError):
                        gauge.remove(camera_id)
        for kind, publisher in [("events", supervisor.events), ("analytics", supervisor.analytics)]:
            self.queues.labels(kind).set(publisher.queue.qsize() if publisher else 0)
            self.dropped.labels(kind).set(publisher.dropped if publisher else 0)
            self.delivery_healthy.labels(kind).set(int(publisher.healthy) if publisher else 1)
        self.detector_info.info(
            {
                name: supervisor.detector_info.get(name, "unknown")
                for name in ["backend", "model", "device", "inference_threads"]
            }
        )
        self.redis_healthy.set(int(supervisor.heartbeat.redis_ok))
        self.cuda_enabled.set(int(supervisor.detector_info.get("device") == "cuda"))
        return generate_latest(self.registry)
