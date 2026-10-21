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
        await conn.execute(text("TRUNCATE zones, camera_configs, cameras"))
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


def test_detection_config_defaults_replace_reset_and_spec(
    client: TestClient, commands: redis.client.PubSub
) -> None:
    camera_id = client.post("/api/v1/cameras", json=MOCK).json()["id"]
    url = f"/api/v1/cameras/{camera_id}/config"
    config = client.get(url).json()
    assert config["overrides"] == dict.fromkeys(config["defaults"])
    assert config["effective"] == config["defaults"]
    saved = client.put(url, json={"target_fps": 3, "detection_confidence": 0.8})
    assert saved.status_code == 200
    assert saved.json()["effective"] == {
        **config["defaults"],
        "target_fps": 3,
        "detection_confidence": 0.8,
    }
    assert next_command(commands)["type"] == "camera.changed"
    spec = client.get(f"/api/v1/internal/worker/cameras/{camera_id}", headers=AUTH)
    assert spec.status_code == 200
    assert spec.json()["config"] == saved.json()["effective"]
    # PUT replaces, not patches: omitted threshold is inherited again.
    saved = client.put(url, json={"target_fps": 4}).json()
    assert saved["overrides"]["detection_confidence"] is None
    assert client.put(url, json={}).json()["effective"] == config["defaults"]
    assert client.put(url, json={"target_fps": 31}).status_code == 422
    assert client.put(url, json={"detection_confidence": 0}).status_code == 422
    client.delete(f"/api/v1/cameras/{camera_id}")
    assert client.get(url).status_code == 404
    assert client.put(url, json={}).status_code == 404


ZONE_BODY = {
    "name": "Проход",
    "points": [
        {"x": 0.2, "y": 0.2},
        {"x": 0.8, "y": 0.2},
        {"x": 0.8, "y": 0.9},
        {"x": 0.2, "y": 0.9},
    ],
    "enabled": True,
}


def test_zone_crud_and_worker_spec(client: TestClient, commands: redis.client.PubSub) -> None:
    cid = client.post("/api/v1/cameras", json=MOCK).json()["id"]
    url = f"/api/v1/cameras/{cid}/zones"
    assert client.get(url).json() == []
    response = client.post(url, json=ZONE_BODY)
    assert response.status_code == 201, response.text
    zone = response.json()
    assert zone["camera_id"] == cid and zone["points"] == ZONE_BODY["points"]
    assert zone["created_at"] and zone["updated_at"]
    assert next_command(commands)["type"] == "camera.changed"
    assert client.get(url).json() == [zone]
    spec_url = f"/api/v1/internal/worker/cameras/{cid}"
    spec = client.get(spec_url, headers=AUTH).json()
    assert spec["zones"][0]["id"] == zone["id"]
    updated = client.put(
        f"{url}/{zone['id']}", json={**ZONE_BODY, "name": "Новая", "enabled": False}
    )
    assert updated.status_code == 200 and not updated.json()["enabled"]
    assert next_command(commands)["type"] == "camera.changed"
    assert not client.get(spec_url, headers=AUTH).json()["zones"][0]["enabled"]
    assert client.delete(f"{url}/{zone['id']}").status_code == 204
    assert next_command(commands)["type"] == "camera.changed"
    assert client.get(url).json() == []
    assert client.get(spec_url, headers=AUTH).json()["zones"] == []
    assert client.delete(f"{url}/{zone['id']}").status_code == 404


def test_zone_camera_scoping_and_deleted_parent(client: TestClient) -> None:
    cid = client.post("/api/v1/cameras", json=MOCK).json()["id"]
    other = client.post("/api/v1/cameras", json={**MOCK, "name": "Другой"}).json()["id"]
    url = f"/api/v1/cameras/{cid}/zones"
    zid = client.post(url, json=ZONE_BODY).json()["id"]
    wrong = f"/api/v1/cameras/{other}/zones/{zid}"
    assert client.put(wrong, json=ZONE_BODY).status_code == 404
    assert client.delete(wrong).status_code == 404
    assert len(client.get(url).json()) == 1
    client.delete(f"/api/v1/cameras/{cid}")
    assert client.get(url).status_code == 404
    assert client.post(url, json=ZONE_BODY).status_code == 404
    assert client.put(f"{url}/{zid}", json=ZONE_BODY).status_code == 404
    assert client.delete(f"{url}/{zid}").status_code == 404


def test_zone_invalid_geometry_and_capacity(client: TestClient) -> None:
    cid = client.post("/api/v1/cameras", json=MOCK).json()["id"]
    url = f"/api/v1/cameras/{cid}/zones"
    for points in [
        [],
        [{"x": 0, "y": 0}] * 3,
        [{"x": 0, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}, {"x": 1, "y": 0}],
        [{"x": -1, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}],
    ]:
        assert client.post(url, json={**ZONE_BODY, "points": points}).status_code == 422
    assert client.get(url).json() == []
    for _ in range(16):
        assert client.post(url, json=ZONE_BODY).status_code == 201
    assert client.post(url, json=ZONE_BODY).status_code == 422
    assert len(client.get(url).json()) == 16


def test_zone_timing_overrides_persist_and_resolve(client: TestClient) -> None:
    cid = client.post("/api/v1/cameras", json=MOCK).json()["id"]
    url = f"/api/v1/cameras/{cid}/config"
    timings = {
        "zone_enter_dwell_seconds": 0,
        "zone_exit_grace_seconds": 1.5,
        "event_cooldown_seconds": 8,
    }
    response = client.put(url, json=timings)
    assert response.status_code == 200
    assert all(response.json()["effective"][k] == v for k, v in timings.items())
    assert client.get(url).json() == response.json()
    spec = client.get(f"/api/v1/internal/worker/cameras/{cid}", headers=AUTH).json()
    assert spec["config"] == response.json()["effective"]
    for key in timings:
        assert client.put(url, json={key: -1}).status_code == 422
    reset = client.put(url, json={}).json()
    assert reset["effective"] == reset["defaults"]
