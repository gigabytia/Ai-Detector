import uuid
from datetime import UTC, datetime
from types import TracebackType
from typing import cast

from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from ai_detector_core.cameras.status import CameraRuntimeStatus, CameraStatus
from ai_detector_core.telemetry.redis_keys import CAMERA_STATUS_TTL_SECONDS, camera_status_key
from vision_worker.messaging.camera_status import CameraStatusPublisher


class FakePipeline:
    def __init__(self, store: "FakeRedis") -> None:
        self.store = store
        self.ops: list[tuple[str, str, str | None, int | None]] = []

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def set(self, key: str, value: str, ex: int) -> None:
        self.ops.append(("set", key, value, ex))

    def delete(self, key: str) -> None:
        self.ops.append(("delete", key, None, None))

    async def execute(self) -> None:
        if self.store.down:
            raise RedisConnectionError("down")
        for op, key, value, ex in self.ops:
            if op == "set":
                self.store.values[key] = (value, ex)
            else:
                self.store.values.pop(key, None)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str | None, int | None]] = {}
        self.down = False

    def pipeline(self, transaction: bool) -> FakePipeline:
        return FakePipeline(self)


def status(camera_id: uuid.UUID) -> CameraRuntimeStatus:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return CameraRuntimeStatus(
        camera_id=camera_id,
        run_id=uuid.uuid4(),
        worker_id="w",
        status=CameraStatus.RUNNING,
        capture_fps=15.0,
        frame_size=(1280, 720),
        last_frame_at=now,
        last_error=None,
        reconnect_attempts=0,
        last_reconnect_attempt_at=None,
        updated_at=now,
    )


async def test_publishes_with_ttl_and_withdraws_gone_cameras() -> None:
    redis = FakeRedis()
    a, b = uuid.uuid4(), uuid.uuid4()
    current = [status(a), status(b)]
    publisher = CameraStatusPublisher(cast(Redis, redis), lambda: current)

    await publisher.publish_once()
    value, ttl = redis.values[camera_status_key(a)]
    assert ttl == CAMERA_STATUS_TTL_SECONDS
    assert CameraRuntimeStatus.model_validate_json(value or "").camera_id == a

    current = [status(a)]
    await publisher.publish_once()
    assert camera_status_key(b) not in redis.values


async def test_redis_outage_does_not_raise_and_recovers() -> None:
    redis = FakeRedis()
    a, b = uuid.uuid4(), uuid.uuid4()
    current = [status(a), status(b)]
    publisher = CameraStatusPublisher(cast(Redis, redis), lambda: current)
    await publisher.publish_once()

    redis.down = True
    current = [status(a)]
    await publisher.publish_once()  # logged, not raised

    redis.down = False
    await publisher.publish_once()
    assert camera_status_key(b) not in redis.values  # withdrawal retried after recovery
