"""HTTP readiness and websocket boundary checks, without model startup."""

import asyncio
import uuid
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ai_detector_core.cameras.status import CameraStatus
from vision_worker.http.app import create_http_app
from vision_worker.pipeline.preview import PreviewHub
from vision_worker.supervisor import Supervisor


def supervisor(*, healthy: bool = True, redis_ok: bool = True) -> Supervisor:
    return cast(
        Supervisor,
        SimpleNamespace(
            heartbeat=SimpleNamespace(redis_ok=redis_ok, last_published_at=None),
            scheduler=SimpleNamespace(healthy=healthy),
            events=None,
            detector_info={"backend": "test"},
            manager=SimpleNamespace(sessions=[]),
            preview=PreviewHub(),
        ),
    )


def test_readiness_requires_redis_and_inference_loop() -> None:
    for healthy, redis_ok in [(True, True), (False, True), (True, False)]:
        sup = supervisor(healthy=healthy, redis_ok=redis_ok)
        client = TestClient(create_http_app(sup))
        response = client.get("/health/ready")
        assert response.status_code == (200 if healthy and redis_ok else 503)
        assert response.json()["detector_loaded"] is True
        sup.preview._pool.shutdown()


def test_preview_unknown_camera_and_untrusted_origin_are_rejected() -> None:
    sup = supervisor()
    client = TestClient(create_http_app(sup))
    with (
        pytest.raises(WebSocketDisconnect) as error,
        client.websocket_connect(f"/cameras/{uuid.uuid4()}/preview"),
    ):
        pass
    assert error.value.code == 1008
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            f"/cameras/{uuid.uuid4()}/preview", headers={"origin": "https://evil.example"}
        ),
    ):
        pass
    assert not sup.preview._viewers
    sup.preview._pool.shutdown()


def test_preview_packet_and_subscription_cleanup() -> None:
    class PreloadedHub(PreviewHub):
        def subscribe(self, camera_id: uuid.UUID) -> asyncio.Queue[bytes]:
            queue = super().subscribe(camera_id)
            queue.put_nowait(b"packet")
            return queue

    camera_id = uuid.uuid4()
    hub = PreloadedHub()
    session = SimpleNamespace(spec=SimpleNamespace(id=camera_id), state=CameraStatus.RUNNING)
    sup = cast(
        Supervisor, SimpleNamespace(manager=SimpleNamespace(sessions=[session]), preview=hub)
    )
    client = TestClient(create_http_app(sup))
    with client.websocket_connect(f"/cameras/{camera_id}/preview") as socket:
        assert socket.receive_bytes() == b"packet"
    assert not hub._viewers
    hub._pool.shutdown()


def test_disconnected_viewer_is_removed_without_any_new_frames() -> None:
    camera_id = uuid.uuid4()
    hub = PreviewHub()
    session = SimpleNamespace(spec=SimpleNamespace(id=camera_id), state=CameraStatus.RECONNECTING)
    sup = cast(
        Supervisor, SimpleNamespace(manager=SimpleNamespace(sessions=[session]), preview=hub)
    )
    client = TestClient(create_http_app(sup))
    with client.websocket_connect(f"/cameras/{camera_id}/preview"):
        assert camera_id in hub._viewers
    assert not hub._viewers
    hub._pool.shutdown()


def test_telemetry_is_json_and_cleans_up_without_jpeg_encoding() -> None:
    from vision_worker.pipeline.telemetry import TelemetryHub

    class PreloadedTelemetry(TelemetryHub):
        def subscribe(self, camera_id: uuid.UUID) -> asyncio.Queue[str]:
            queue = super().subscribe(camera_id)
            queue.put_nowait('{"version":1,"persons":2}')
            return queue

    camera_id = uuid.uuid4()
    hub = PreloadedTelemetry()
    session = SimpleNamespace(spec=SimpleNamespace(id=camera_id), state=CameraStatus.RUNNING)
    sup = cast(
        Supervisor, SimpleNamespace(manager=SimpleNamespace(sessions=[session]), telemetry=hub)
    )
    client = TestClient(create_http_app(sup))
    with client.websocket_connect(f"/cameras/{camera_id}/telemetry") as socket:
        assert socket.receive_json() == {"version": 1, "persons": 2}
    assert not hub._subscribers


def test_telemetry_rejects_unknown_camera_and_bad_origin() -> None:
    sup = supervisor()
    client = TestClient(create_http_app(sup))
    for headers in [{}, {"origin": "https://evil.example"}]:
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(f"/cameras/{uuid.uuid4()}/telemetry", headers=headers),
        ):
            pass
    sup.preview._pool.shutdown()
