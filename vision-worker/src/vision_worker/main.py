"""Worker entry point: builds dependencies explicitly (no global singletons) and serves HTTP."""

import logging

import uvicorn
from redis.asyncio import Redis

from ai_detector_core.observability.json_logging import configure_json_logging
from ai_detector_core.ports.clock import SystemClock
from ai_detector_core.storage.snapshots import LocalSnapshotStorage
from vision_worker import __version__
from vision_worker.cameras.factory import CameraSessionFactory
from vision_worker.cameras.manager import CameraManager
from vision_worker.cameras.reconnect import BackoffPolicy
from vision_worker.cameras.spec_client import CameraSpecClient, create_api_http_client
from vision_worker.config import WorkerSettings, get_settings
from vision_worker.http.app import create_http_app
from vision_worker.inference.adapters.ultralytics import UltralyticsPersonDetector
from vision_worker.messaging.analytics import AnalyticsPublisher
from vision_worker.messaging.camera_status import CameraStatusPublisher
from vision_worker.messaging.commands import CommandListener
from vision_worker.messaging.events import EventPublisher
from vision_worker.messaging.heartbeat import HeartbeatPublisher
from vision_worker.pipeline.analytics import AnalyticsCollector
from vision_worker.pipeline.preview import PreviewHub
from vision_worker.pipeline.scheduler import InferenceScheduler
from vision_worker.pipeline.telemetry import TelemetryHub
from vision_worker.rules.registry import SceneRegistry
from vision_worker.storage.snapshot_writer import SnapshotWriter
from vision_worker.supervisor import Supervisor
from vision_worker.tracking.bytetrack import ByteTrackPersonTracker
from vision_worker.tracking.registry import TrackerRegistry

logger = logging.getLogger(__name__)


def build_supervisor(settings: WorkerSettings) -> Supervisor:
    # Must complete before HTTP startup. Never auto-download weights or fall back to scripted.
    detector = UltralyticsPersonDetector(
        settings.model_manifest_path,
        settings.inference_device,
        settings.detection_iou,
        settings.inference_threads,
    )
    clock = SystemClock()
    redis = Redis.from_url(str(settings.redis_url), socket_connect_timeout=2, socket_timeout=5)
    backoff = BackoffPolicy(
        initial_seconds=settings.reconnect_initial_delay_seconds,
        max_seconds=settings.reconnect_max_delay_seconds,
    )
    token = settings.worker_api_token.get_secret_value() if settings.worker_api_token else None
    if token is None:
        logger.error("WORKER_API_TOKEN is not set; cameras cannot be loaded from the API")
    api_http = create_api_http_client(str(settings.api_base_url), token)
    manager = CameraManager(
        CameraSessionFactory(
            upload_root=settings.upload_path,
            backoff=backoff,
            worker_id=settings.worker_id,
            clock=clock,
        )
    )
    preview = PreviewHub(settings.preview_fps, settings.preview_max_width)
    events = EventPublisher(redis)
    analytics = AnalyticsPublisher(redis)
    telemetry = TelemetryHub()
    snapshots = SnapshotWriter(LocalSnapshotStorage(settings.snapshot_path), events)
    return Supervisor(
        analytics=analytics,
        snapshots=snapshots,
        events=events,
        telemetry=telemetry,
        scheduler=InferenceScheduler(
            manager,
            detector,
            preview,
            settings.inference_batch_size,
            settings.inference_max_wait_ms,
            analytics=AnalyticsCollector(analytics),
            snapshots=snapshots,
            events=events,
            telemetry=telemetry,
            scenes=SceneRegistry(
                clock,
                settings.event_min_track_hits,
                settings.severity_zone_enter,
                settings.line_hysteresis,
                settings.severity_line_cross,
            ),
            trackers=TrackerRegistry(
                lambda camera_id, run_id: ByteTrackPersonTracker(
                    camera_id,
                    run_id,
                    settings.person_track_max_age,
                    settings.track_match_iou,
                    settings.track_activation_confidence,
                )
            ),
        ),
        preview=preview,
        detector_info={
            "backend": "ultralytics",
            "model": detector.manifest.name,
            "device": detector.device,
        },
        redis=redis,
        api_http=api_http,
        heartbeat=HeartbeatPublisher(
            store=redis, worker_id=settings.worker_id, version=__version__, clock=clock
        ),
        manager=manager,
        commands=CommandListener(
            redis=redis,
            specs=CameraSpecClient(api_http),
            manager=manager,
            retry=backoff,
            reconcile_interval_seconds=settings.reconcile_interval_seconds,
        ),
        camera_status=CameraStatusPublisher(
            redis=redis, statuses=lambda: [s.status() for s in manager.sessions]
        ),
    )


def run() -> None:
    settings = get_settings()
    configure_json_logging(service="vision-worker", level=settings.log_level)
    try:
        supervisor = build_supervisor(settings)
    except Exception:
        logger.critical("person detector not loaded; worker cannot start", exc_info=True)
        raise SystemExit(1) from None
    app = create_http_app(supervisor, settings.preview_allowed_origins)
    uvicorn.run(
        app, host=settings.worker_http_host, port=settings.worker_http_port, log_config=None
    )


if __name__ == "__main__":
    run()
