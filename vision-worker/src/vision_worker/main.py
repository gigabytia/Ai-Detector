"""Worker entry point: builds dependencies explicitly and serves the HTTP app."""

import uvicorn
from redis.asyncio import Redis

from ai_detector_core.observability.json_logging import configure_json_logging
from ai_detector_core.ports.clock import SystemClock
from vision_worker import __version__
from vision_worker.config import WorkerSettings, get_settings
from vision_worker.http.app import create_http_app
from vision_worker.messaging.heartbeat import HeartbeatPublisher
from vision_worker.supervisor import Supervisor


def build_supervisor(settings: WorkerSettings) -> Supervisor:
    redis = Redis.from_url(str(settings.redis_url), socket_connect_timeout=2, socket_timeout=2)
    heartbeat = HeartbeatPublisher(
        store=redis, worker_id=settings.worker_id, version=__version__, clock=SystemClock()
    )
    return Supervisor(redis=redis, heartbeat=heartbeat)


def run() -> None:
    settings = get_settings()
    configure_json_logging(service="vision-worker", level=settings.log_level)
    app = create_http_app(build_supervisor(settings))
    uvicorn.run(
        app, host=settings.worker_http_host, port=settings.worker_http_port, log_config=None
    )


if __name__ == "__main__":
    run()
