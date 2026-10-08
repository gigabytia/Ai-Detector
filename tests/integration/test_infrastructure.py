from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from app.core.config import Settings
from app.main import create_app
from fakes import FixedClock
from vision_worker.messaging.heartbeat import HeartbeatPublisher

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"


def test_alembic_upgrade_head_runs(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", str(settings.database_url))
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def test_ready_with_real_dependencies(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200, response.text
    assert all(item["ok"] for item in response.json()["dependencies"])


def test_not_ready_when_redis_unreachable(settings: Settings) -> None:
    broken = settings.model_copy(update={"redis_url": "redis://127.0.0.1:1/0"})
    with TestClient(create_app(broken)) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    redis_status = next(d for d in response.json()["dependencies"] if d["name"] == "redis")
    assert redis_status["ok"] is False


async def test_worker_heartbeat_visible_in_system_status(settings: Settings) -> None:
    redis = Redis.from_url(str(settings.redis_url))
    publisher = HeartbeatPublisher(
        store=redis, worker_id="it-worker", version="0.1.0", clock=FixedClock()
    )
    try:
        await publisher.publish_once()
        assert publisher.redis_ok
        with TestClient(create_app(settings)) as client:
            body = client.get("/api/v1/system/status").json()
        assert "it-worker" in [w["worker_id"] for w in body["workers"]]
    finally:
        await publisher.withdraw()
        await redis.aclose()
