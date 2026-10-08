"""Worker entry point: builds dependencies explicitly (no global singletons) and serves HTTP."""

import logging

import uvicorn
from redis.asyncio import Redis

from ai_detector_core.observability.json_logging import configure_json_logging
from ai_detector_core.ports.clock import SystemClock
from vision_worker import __version__
from vision_worker.cameras.factory import CameraSessionFactory
from vision_worker.cameras.manager import CameraManager
from vision_worker.cameras.reconnect import BackoffPolicy
from vision_worker.cameras.spec_client import CameraSpecClient, create_api_http_client
from vision_worker.config import WorkerSettings, get_settings
from vision_worker.http.app import create_http_app
from vision_worker.messaging.camera_status import CameraStatusPublisher
from vision_worker.messaging.commands import CommandListener
from vision_worker.messaging.heartbeat import HeartbeatPublisher
from vision_worker.supervisor import Supervisor

logger = logging.getLogger(__name__)


def build_supervisor(settings: WorkerSettings) -> Supervisor:
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
    return Supervisor(
        redis=redis,
        api_http=api_http,
        heartbeat=HeartbeatPublisher(
            store=redis, worker_id=settings.worker_id, version=__version__, clock=clock
        ),
        manager=manager,
        commands=CommandListener(
            redis=redis, specs=CameraSpecClient(api_http), manager=manager, retry=backoff
        ),
        camera_status=CameraStatusPublisher(
            redis=redis, statuses=lambda: [s.status() for s in manager.sessions]
        ),
    )


def run() -> None:
    settings = get_settings()
    configure_json_logging(service="vision-worker", level=settings.log_level)
    app = create_http_app(build_supervisor(settings))
    uvicorn.run(
        app, host=settings.worker_http_host, port=settings.worker_http_port, log_config=None
    )


if __name__ == "__main__":
    run()
