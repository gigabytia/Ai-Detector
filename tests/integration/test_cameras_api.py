"""Camera, upload and internal worker API against real PostgreSQL and Redis.

Requires the schema (`make migrate`). Each test truncates the cameras table.
"""

import asyncio
import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import redis
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ai_detector_core.telemetry.redis_keys import WORKER_COMMANDS_CHANNEL
from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.integration

TOKEN = "integration-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
MOCK = {"name": "Склад", "source_type": "mock", "source_url": "mock://walk_through"}


async def _truncate(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE cameras"))
    await engine.dispose()


@pytest.fixture
def client(settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    asyncio.run(_truncate(str(settings.database_url)))
    configured = settings.model_copy(
        update={
            "worker_api_token": SecretStr(TOKEN),
            "upload_path": tmp_path,
            "max_cameras": 3,
            "upload_max_bytes": 1024,
        }
    )
    with TestClient(create_app(configured)) as test_client:
        yield test_client


@pytest.fixture
def commands(settings: Settings) -> Iterator[redis.client.PubSub]:
    connection = redis.Redis.from_url(str(settings.redis_url))
    pubsub = connection.pubsub(ignore_subscribe_messages=True)  # type: ignore[no-untyped-call]
    pubsub.subscribe(WORKER_COMMANDS_CHANNEL)
    pubsub.get_message(timeout=1)  # consume the subscribe confirmation
    yield pubsub
    pubsub.close()
    connection.close()


def next_command(pubsub: redis.client.PubSub) -> dict[str, str]:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        message = pubsub.get_message(timeout=0.2)
        if message is not None:
            result: dict[str, str] = json.loads(message["data"])
            return result
    raise AssertionError("no worker command published")


def test_camera_crud_and_soft_delete(client: TestClient) -> None:
    created = client.post("/api/v1/cameras", json=MOCK)
    assert created.status_code == 201
    camera = created.json()
    assert camera["enabled"] is False
    assert camera["runtime"] is None

    assert client.post("/api/v1/cameras", json=MOCK).json()["error"]["code"] == (
        "CAMERA_ALREADY_EXISTS"
    )

    renamed = client.patch(f"/api/v1/cameras/{camera['id']}", json={"name": "Склад 2"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Склад 2"
    assert [c["name"] for c in client.get("/api/v1/cameras").json()] == ["Склад 2"]

    assert client.delete(f"/api/v1/cameras/{camera['id']}").status_code == 204
    assert client.get(f"/api/v1/cameras/{camera['id']}").status_code == 404
    assert client.get("/api/v1/cameras").json() == []
    # The name of a deleted camera can be reused (partial unique index).
    assert client.post("/api/v1/cameras", json={**MOCK, "name": "Склад 2"}).status_code == 201


def test_rtsp_credentials_are_masked(client: TestClient) -> None:
    body = {"name": "Вход", "source_type": "rtsp", "source_url": "rtsp://admin:pw@10.0.0.5/s"}
    camera = client.post("/api/v1/cameras", json=body).json()
    assert camera["source_url"] == "rtsp://***:***@10.0.0.5/s"
    assert "pw" not in client.get("/api/v1/cameras").text


def test_validation_and_limits(client: TestClient) -> None:
    bad = client.post("/api/v1/cameras", json={**MOCK, "source_url": "file:///etc/passwd"})
    assert bad.status_code == 422
    missing = {"name": "Файл", "source_type": "file", "source_url": f"upload://{'a' * 32}.mp4"}
    assert client.post("/api/v1/cameras", json=missing).status_code == 422

    for i in range(3):
        assert client.post("/api/v1/cameras", json={**MOCK, "name": f"c{i}"}).status_code == 201
    limit = client.post("/api/v1/cameras", json={**MOCK, "name": "c4"})
    assert limit.status_code == 422
    assert limit.json()["error"]["code"] == "CAMERA_LIMIT_REACHED"


def test_desired_state_changes_publish_commands(
    client: TestClient, commands: redis.client.PubSub
) -> None:
    camera = client.post("/api/v1/cameras", json={**MOCK, "enabled": True}).json()
    assert next_command(commands) == {"type": "camera.changed", "camera_id": camera["id"]}

    stopped = client.post(f"/api/v1/cameras/{camera['id']}/stop")
    assert stopped.json()["enabled"] is False
    assert next_command(commands)["type"] == "camera.changed"

    restarted = client.post(f"/api/v1/cameras/{camera['id']}/restart")
    assert restarted.json()["enabled"] is True
    assert next_command(commands) == {"type": "camera.restart", "camera_id": camera["id"]}


def test_upload_then_file_camera(client: TestClient, tmp_path: Path) -> None:
    upload = client.post("/api/v1/uploads", files={"file": ("../../clip.MP4", b"x" * 100)})
    assert upload.status_code == 201
    body = upload.json()
    assert (tmp_path / body["file_ref"]).read_bytes() == b"x" * 100
    assert body["source_url"].startswith("upload://")
    camera = {"name": "Видео", "source_type": "file", "source_url": body["source_url"]}
    assert client.post("/api/v1/cameras", json=camera).status_code == 201

    too_big = client.post("/api/v1/uploads", files={"file": ("big.mp4", b"x" * 2048)})
    assert too_big.status_code == 413
    wrong_type = client.post("/api/v1/uploads", files={"file": ("run.sh", b"echo")})
    assert wrong_type.status_code == 422
    assert sorted(p.name for p in tmp_path.iterdir()) == [body["file_ref"]]  # no leftovers


def test_internal_worker_api_requires_token(client: TestClient) -> None:
    enabled = client.post("/api/v1/cameras", json={**MOCK, "enabled": True}).json()
    client.post("/api/v1/cameras", json={**MOCK, "name": "выкл"})

    assert client.get("/api/v1/internal/worker/cameras").status_code == 401
    wrong = {"Authorization": "Bearer nope"}
    assert client.get("/api/v1/internal/worker/cameras", headers=wrong).status_code == 401

    specs = client.get("/api/v1/internal/worker/cameras", headers=AUTH).json()
    assert [s["id"] for s in specs] == [enabled["id"]]
    assert specs[0]["source_url"] == "mock://walk_through"  # unmasked for the worker
    client.delete(f"/api/v1/cameras/{enabled['id']}")
    gone = client.get(f"/api/v1/internal/worker/cameras/{enabled['id']}", headers=AUTH)
    assert gone.status_code == 404
