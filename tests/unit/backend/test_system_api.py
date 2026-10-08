from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from ai_detector_core.telemetry.heartbeat import WorkerHeartbeat
from app.api.deps import get_system_service
from app.application.system_service import SystemService
from app.core.config import Settings
from app.main import create_app
from fakes import FixedClock


class FakeProbe:
    def __init__(self, name: str, error: Exception | None = None) -> None:
        self.name = name
        self.error = error

    async def check(self) -> None:
        if self.error is not None:
            raise self.error


class FakeHeartbeats:
    def __init__(self, items: list[WorkerHeartbeat]) -> None:
        self.items = items
        self.calls = 0

    async def list_heartbeats(self) -> list[WorkerHeartbeat]:
        self.calls += 1
        return self.items


CLOCK = FixedClock(datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC))
WORKER = WorkerHeartbeat(
    worker_id="worker-1",
    version="0.1.0",
    started_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    sent_at=datetime(2026, 1, 1, 12, 0, 29, tzinfo=UTC),
)


def make_client(service: SystemService) -> Iterator[TestClient]:
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_system_service] = lambda: service
    with TestClient(app) as client:
        yield client


@pytest.fixture
def healthy_client() -> Iterator[TestClient]:
    service = SystemService(
        probes=[FakeProbe("database"), FakeProbe("redis")],
        heartbeats=FakeHeartbeats([WORKER]),
        redis_probe_name="redis",
        clock=CLOCK,
    )
    yield from make_client(service)


@pytest.fixture
def heartbeats() -> FakeHeartbeats:
    return FakeHeartbeats([WORKER])


@pytest.fixture
def redis_down_client(heartbeats: FakeHeartbeats) -> Iterator[TestClient]:
    service = SystemService(
        probes=[FakeProbe("database"), FakeProbe("redis", ConnectionError("refused"))],
        heartbeats=heartbeats,
        redis_probe_name="redis",
        clock=CLOCK,
    )
    yield from make_client(service)


def test_live_does_not_depend_on_dependencies(redis_down_client: TestClient) -> None:
    response = redis_down_client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_ready_when_all_dependencies_ok(healthy_client: TestClient) -> None:
    response = healthy_client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_not_ready_returns_503_with_failed_dependency(redis_down_client: TestClient) -> None:
    response = redis_down_client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert {"name": "redis", "ok": False, "error": "ConnectionError"} in body["dependencies"]


def test_system_status_lists_workers(healthy_client: TestClient) -> None:
    body = healthy_client.get("/api/v1/system/status").json()
    assert body["status"] == "ok"
    assert body["workers"] == [
        {
            "worker_id": "worker-1",
            "version": "0.1.0",
            "started_at": "2026-01-01T12:00:00Z",
            "last_seen_at": "2026-01-01T12:00:29Z",
            "uptime_seconds": 30.0,
        }
    ]


def test_system_status_degraded_without_redis_skips_worker_lookup(
    redis_down_client: TestClient, heartbeats: FakeHeartbeats
) -> None:
    body = redis_down_client.get("/api/v1/system/status").json()
    assert body["status"] == "degraded"
    assert body["workers"] == []
    assert heartbeats.calls == 0


def test_unknown_route_uses_error_envelope(healthy_client: TestClient) -> None:
    response = healthy_client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_ERROR"
