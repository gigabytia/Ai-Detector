"""Real PostgreSQL/Valkey: delivery, replay, poison messages, REST and live fanout."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import RedisDsn
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_detector_core.events.domain import DomainEvent, ZoneEntryMetadata
from ai_detector_core.telemetry.event_bus import (
    DEAD_STREAM,
    INGEST_GROUP,
    INGEST_STREAM,
    pending_event_key,
)
from app.core.config import Settings
from app.infrastructure.database.models import CameraModel, EventModel
from app.infrastructure.redis.ingest import EventIngest, stream_messages
from app.infrastructure.redis.live import LiveHub
from app.main import create_app
from vision_worker.messaging.events import EventPublisher

pytestmark = pytest.mark.integration


@pytest.fixture
async def transport(
    settings: Settings,
) -> AsyncIterator[tuple[Redis, async_sessionmaker[AsyncSession], Settings]]:
    configured = settings.model_copy(
        update={"redis_url": RedisDsn(str(settings.redis_url).rsplit("/", 1)[0] + "/13")}
    )
    redis = Redis.from_url(str(configured.redis_url))
    await redis.flushdb()  # dedicated integration DB 13 only
    engine = create_async_engine(str(settings.database_url))
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE events, lines, zones, camera_configs, cameras CASCADE"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    yield redis, sessions, configured
    await redis.flushdb()
    await redis.aclose()
    await engine.dispose()


async def make_event(sessions: async_sessionmaker[AsyncSession]) -> DomainEvent:
    camera_id = uuid4()
    async with sessions() as session, session.begin():
        session.add(
            CameraModel(
                id=camera_id,
                name=str(camera_id),
                source_type="mock",
                source_url="mock://walk_through",
                enabled=False,
            )
        )
    return DomainEvent(
        camera_id=camera_id,
        run_id=uuid4(),
        track_id=7,
        zone_id=uuid4(),
        occurred_at=datetime.now(UTC),
        source_ts_ms=100,
        detector_confidence=0.8,
        event_confidence=0.7,
        message="Вход",
        metadata=ZoneEntryMetadata(
            bbox=(0.1, 0.1, 0.5, 0.5), anchor=(0.3, 0.5), dwell_seconds=1, stability=0.9
        ),
    )


async def read_batch(ingest: EventIngest) -> list[tuple[bytes, dict[bytes, bytes]]]:
    await ingest.ensure_group()
    return stream_messages(
        await ingest.redis.xreadgroup(
            INGEST_GROUP, ingest.consumer, {INGEST_STREAM: ">"}, count=200
        )
    )


async def test_duplicate_delivery_does_not_overwrite_operator_state(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    redis, sessions, _ = transport
    event = await make_event(sessions)
    publisher = EventPublisher(redis)
    ingest = EventIngest(redis, sessions)
    await publisher.publish(event)
    await publisher.publish(event)
    await ingest.process(await read_batch(ingest))
    async with sessions() as session:
        rows = list(await session.scalars(select(EventModel)))
        assert len(rows) == 1 and rows[0].zone_id is None  # deleted before ingest
        rows[0].status = "ACKNOWLEDGED"
        rows[0].note = "checked"
        await session.commit()
    await publisher.publish(event)
    await ingest.process(await read_batch(ingest))
    async with sessions() as session:
        row = await session.get(EventModel, event.id)
        assert row and row.status == "ACKNOWLEDGED" and row.note == "checked"
    assert await redis.xlen(INGEST_STREAM) == 0
    assert (await redis.xpending(INGEST_STREAM, INGEST_GROUP))["pending"] == 0


async def test_commit_failure_leaves_pending_for_recovery(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    redis, sessions, _ = transport
    event = await make_event(sessions)
    await EventPublisher(redis).publish(event)
    ingest = EventIngest(redis, sessions)
    messages = await read_batch(ingest)
    bad_engine = create_async_engine(
        "postgresql+asyncpg://no@127.0.0.1:1/no", connect_args={"timeout": 0.2}
    )
    broken = EventIngest(redis, async_sessionmaker(bad_engine))
    with pytest.raises((OSError, OperationalError)):
        await broken.process(messages)
    assert (await redis.xpending(INGEST_STREAM, INGEST_GROUP))["pending"] == 1
    await bad_engine.dispose()
    # Simulate a dead consumer's idle pending entry without waiting 30 seconds.
    recovered = EventIngest(redis, sessions)
    claimed = await redis.xautoclaim(INGEST_STREAM, INGEST_GROUP, recovered.consumer, 0)
    await recovered.process(claimed[1])
    assert await redis.xlen(INGEST_STREAM) == 0
    async with sessions() as session:
        assert await session.get(EventModel, event.id)


async def test_poison_message_dead_letter_does_not_block_good_event(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    redis, sessions, _ = transport
    event = await make_event(sessions)
    await redis.xadd(INGEST_STREAM, {"event": "not json"})
    await redis.xadd(INGEST_STREAM, {"other": "field"})
    await EventPublisher(redis).publish(event.model_copy(update={"camera_id": uuid4()}))
    await EventPublisher(redis).publish(event)
    ingest = EventIngest(redis, sessions)
    await ingest.process(await read_batch(ingest))
    assert await redis.xlen(DEAD_STREAM) == 3
    assert await redis.xlen(INGEST_STREAM) == 0
    async with sessions() as session:
        assert await session.get(EventModel, event.id)


async def test_pubsub_alarm_is_independent_of_database(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    redis, sessions, _ = transport
    event = await make_event(sessions)
    hub = LiveHub(redis)
    queue = hub.subscribe()
    stop = asyncio.Event()
    task = asyncio.create_task(hub.run(stop))
    try:
        initial = await asyncio.wait_for(queue.get(), 2)
        assert initial and "resync" in initial  # subscribed
        await EventPublisher(redis).publish(event)
        packet = await asyncio.wait_for(queue.get(), 2)
        assert packet and "event.created" in packet and str(event.id) in packet
        async with sessions() as session:
            assert await session.get(EventModel, event.id) is None  # no ingest at all
        assert await redis.xlen(INGEST_STREAM) == 1
    finally:
        stop.set()
        await task
        hub.unsubscribe(queue)


async def test_history_pagination_status_audit_and_deleted_camera(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    redis, sessions, configured = transport
    event = await make_event(sessions)
    ingest = EventIngest(redis, sessions)
    for _ in range(3):
        await EventPublisher(redis).publish(event.model_copy(update={"id": uuid4()}))
    await ingest.process(await read_batch(ingest))
    app = create_app(configured)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        page = (await client.get("/api/v1/events?limit=2")).json()
        assert len(page["items"]) == 2 and page["next_cursor"]
        next_page = (
            await client.get("/api/v1/events", params={"cursor": page["next_cursor"], "limit": 2})
        ).json()
        assert len(next_page["items"]) == 1
        assert len({e["id"] for e in page["items"] + next_page["items"]}) == 3
        event_id = page["items"][0]["id"]
        ack = await client.patch(
            f"/api/v1/events/{event_id}", json={"status": "ACKNOWLEDGED", "note": "Проверено"}
        )
        assert ack.status_code == 200 and ack.json()["acknowledged_at"]
        at = ack.json()["acknowledged_at"]
        same = await client.patch(f"/api/v1/events/{event_id}", json={"status": "ACKNOWLEDGED"})
        assert same.json()["acknowledged_at"] == at and same.json()["note"] == "Проверено"
        conflict = await client.patch(
            f"/api/v1/events/{event_id}", json={"status": "FALSE_POSITIVE"}
        )
        assert conflict.status_code == 409
        assert (await client.get("/api/v1/events", params={"status": "ACKNOWLEDGED"})).json()[
            "items"
        ][0]["id"] == event_id
        assert (
            await client.patch(f"/api/v1/events/{event_id}", json={"note": "x" * 2001})
        ).status_code == 422
        assert (await client.get("/api/v1/events?cursor=bad")).status_code == 422
        assert (await client.get(f"/api/v1/events/{uuid4()}")).status_code == 404
        pending = uuid4()
        await redis.set(pending_event_key(pending), "1", ex=60)
        delayed = await client.patch(f"/api/v1/events/{pending}", json={"status": "ACKNOWLEDGED"})
        assert (
            delayed.status_code == 409
            and delayed.json()["error"]["code"] == "EVENT_NOT_PERSISTED_YET"
        )
        assert (await client.delete(f"/api/v1/cameras/{event.camera_id}")).status_code == 204
        assert len((await client.get("/api/v1/events")).json()["items"]) == 3


async def test_run_reclaims_idle_entry_from_crashed_api(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    redis, sessions, _ = transport
    event = await make_event(sessions)
    await EventPublisher(redis).publish(event)
    abandoned = EventIngest(redis, sessions)
    messages = await read_batch(abandoned)
    await redis.xclaim(
        INGEST_STREAM, INGEST_GROUP, abandoned.consumer, 0, [messages[0][0]], idle=31000
    )
    recovered = EventIngest(redis, sessions)
    stop = asyncio.Event()
    task = asyncio.create_task(recovered.run(stop))
    try:
        for _ in range(50):
            async with sessions() as session:
                if await session.get(EventModel, event.id):
                    break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError("idle event not reclaimed")
    finally:
        stop.set()
        await task
    assert await redis.xlen(INGEST_STREAM) == 0


async def test_commit_then_lost_ack_is_safe_to_retry(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from redis.exceptions import ConnectionError as RedisConnectionError

    redis, sessions, _ = transport
    event = await make_event(sessions)
    await EventPublisher(redis).publish(event)
    ingest = EventIngest(redis, sessions)
    batch = await read_batch(ingest)
    original = redis.pipeline

    def fail_ack(*args: object, **kwargs: object) -> None:
        raise RedisConnectionError("ACK lost")

    monkeypatch.setattr(redis, "pipeline", fail_ack)
    with pytest.raises(RedisConnectionError):
        await ingest.process(batch)
    monkeypatch.setattr(redis, "pipeline", original)
    async with sessions() as session:
        assert await session.get(EventModel, event.id)  # committed before ACK failure
    assert (await redis.xpending(INGEST_STREAM, INGEST_GROUP))["pending"] == 1
    await ingest.process(batch)
    async with sessions() as session:
        assert len(list(await session.scalars(select(EventModel)))) == 1
    assert await redis.xlen(INGEST_STREAM) == 0


async def test_conflicting_operators_are_serialized(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    redis, sessions, configured = transport
    event = await make_event(sessions)
    await EventPublisher(redis).publish(event)
    ingest = EventIngest(redis, sessions)
    await ingest.process(await read_batch(ingest))
    app = create_app(configured)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        responses = await asyncio.gather(
            *(
                client.patch(f"/api/v1/events/{event.id}", json={"status": status})
                for status in ["ACKNOWLEDGED", "FALSE_POSITIVE"]
            )
        )
        assert sorted(r.status_code for r in responses) == [200, 409]
        final = (await client.get(f"/api/v1/events/{event.id}")).json()
        assert bool(final["acknowledged_at"]) != bool(final["false_positive_at"])


async def test_snapshot_delivery_rest_replay_and_missing_file(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
    tmp_path: Path,
) -> None:
    import cv2
    import numpy as np

    from ai_detector_core.events.transport import EventMessage, SnapshotMetadata
    from ai_detector_core.storage.snapshots import LocalSnapshotStorage, snapshot_key
    from app.infrastructure.database.models import SnapshotModel

    redis, sessions, configured = transport
    configured = configured.model_copy(update={"snapshot_path": tmp_path})
    original = await make_event(sessions)
    snapshot_id = uuid4()
    key = snapshot_key(original.camera_id, original.occurred_at, snapshot_id)
    ok, encoded = cv2.imencode(".jpg", np.full((240, 400, 3), 100, np.uint8))
    assert ok
    data = encoded.tobytes()
    storage = LocalSnapshotStorage(tmp_path)
    storage.put(key, data)
    attachment = SnapshotMetadata(
        id=snapshot_id,
        event_id=original.id,
        storage_key=key,
        width=400,
        height=240,
        size_bytes=len(data),
        created_at=datetime.now(UTC),
    )
    message = EventMessage(**original.model_dump(), snapshot=attachment)
    publisher = EventPublisher(redis)
    await publisher.publish(message)
    ingest = EventIngest(redis, sessions)
    batch = await read_batch(ingest)
    await ingest.process(batch)
    # Lost ACK / replay is idempotent for metadata too.
    await ingest.process(batch)
    async with sessions() as session:
        assert len(list(await session.scalars(select(SnapshotModel)))) == 1
        assert len(list(await session.scalars(select(EventModel)))) == 1
    app = create_app(configured)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        url = f"/api/v1/snapshots/{snapshot_id}"
        detail = (await client.get(f"/api/v1/events/{original.id}")).json()
        assert detail["snapshot_url"] == url and detail["snapshot_width"] == 400
        assert detail["snapshot_height"] == 240 and "storage_key" not in detail
        assert (await client.get("/api/v1/events")).json()["items"][0]["snapshot_id"] == str(
            snapshot_id
        )
        image = await client.get(url)
        assert image.status_code == 200 and image.content == data
        assert image.headers["content-type"] == "image/jpeg"
        assert image.headers["x-content-type-options"] == "nosniff"
        assert image.headers["cache-control"] == "private, no-store"
        await client.patch(
            f"/api/v1/events/{original.id}",
            json={"status": "ACKNOWLEDGED", "note": "снимок проверен"},
        )
        await publisher.publish(message)
        # The API background consumer can race this test consumer; either path commits.
        for _ in range(100):
            if await redis.xlen(INGEST_STREAM) == 0:
                break
            await asyncio.sleep(0.01)
        detail = (await client.get(f"/api/v1/events/{original.id}")).json()
        assert detail["status"] == "ACKNOWLEDGED" and detail["note"] == "снимок проверен"
        assert (await client.delete(f"/api/v1/cameras/{original.camera_id}")).status_code == 204
        assert (await client.get(url)).content == data
        storage.delete(key)
        missing = await client.get(url)
        assert (
            missing.status_code == 404 and missing.json()["error"]["code"] == "SNAPSHOT_NOT_FOUND"
        )
        assert (await client.get(f"/api/v1/snapshots/{uuid4()}")).status_code == 404
        assert (await client.get("/api/v1/snapshots/not-a-uuid")).status_code == 422


async def test_bad_optional_snapshot_never_discards_alarm(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    from app.infrastructure.database.models import SnapshotModel

    redis, sessions, _ = transport
    original = await make_event(sessions)
    payload = original.model_dump(mode="json")
    payload["snapshot"] = {"storage_key": "../../etc/passwd"}
    import json

    await redis.xadd(INGEST_STREAM, {"event": json.dumps(payload)})
    ingest = EventIngest(redis, sessions)
    await ingest.process(await read_batch(ingest))
    async with sessions() as session:
        assert await session.get(EventModel, original.id)
        assert not list(await session.scalars(select(SnapshotModel)))
    assert await redis.xlen(DEAD_STREAM) == 0


async def test_retention_keeps_events_recent_files_and_failed_deletions(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os
    from datetime import timedelta

    from ai_detector_core.events.transport import EventMessage, SnapshotMetadata
    from ai_detector_core.storage.snapshots import LocalSnapshotStorage, snapshot_key
    from app.infrastructure.database.models import SnapshotModel
    from app.infrastructure.storage.snapshot_retention import LOCK, SnapshotRetention

    redis, sessions, _ = transport
    storage = LocalSnapshotStorage(tmp_path)
    ingest = EventIngest(redis, sessions, retention_days=365)
    cutoff = datetime.now(UTC) - timedelta(days=30)
    old = cutoff - timedelta(days=1)
    ids, keys = [], []
    for at in [old, old, datetime.now(UTC)]:
        original = await make_event(sessions)
        snapshot_id = uuid4()
        key = snapshot_key(original.camera_id, original.occurred_at, snapshot_id)
        storage.put(key, b"jpeg")
        metadata = SnapshotMetadata(
            id=snapshot_id,
            event_id=original.id,
            storage_key=key,
            width=10,
            height=20,
            size_bytes=4,
            created_at=at,
        )
        await EventPublisher(redis).publish(
            EventMessage(**original.model_dump(), snapshot=metadata)
        )
        ids.append((original.id, snapshot_id))
        keys.append(key)
    await ingest.process(await read_batch(ingest))
    orphan = snapshot_key(uuid4(), old, uuid4())
    storage.put(orphan, b"orphan")
    path = tmp_path / orphan.removeprefix("snapshots/")
    os.utime(path, (old.timestamp(), old.timestamp()))
    temp = path.parent / ".snapshot-crash.part"
    temp.write_bytes(b"partial")
    os.utime(temp, (old.timestamp(), old.timestamp()))
    original_delete = storage.delete

    def fail_one(key: str) -> None:
        if key == keys[1]:
            raise PermissionError("readonly disk")
        original_delete(key)

    monkeypatch.setattr(storage, "delete", fail_one)
    retention = SnapshotRetention(redis, sessions, storage)
    await retention.clean(cutoff)
    async with sessions() as session:
        assert await session.get(SnapshotModel, ids[0][1]) is None
        assert await session.get(SnapshotModel, ids[1][1]) is not None
        assert await session.get(SnapshotModel, ids[2][1]) is not None
        assert len(list(await session.scalars(select(EventModel)))) == 3
    assert not path.exists() and not temp.exists()
    with storage.open(keys[2]) as file:
        assert file.read() == b"jpeg"
    await redis.set(LOCK, "other-api", ex=120)
    assert not await retention.once()
    assert await redis.get(LOCK) == b"other-api"
    await redis.delete(LOCK)
    monkeypatch.setattr(storage, "delete", original_delete)
    assert await retention.once()
    assert await redis.get(LOCK) is None
    async with sessions() as session:
        assert await session.get(SnapshotModel, ids[1][1]) is None
        assert len(list(await session.scalars(select(EventModel)))) == 3


async def test_snapshot_insert_failure_rolls_back_event_before_ack(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    from sqlalchemy import event as sql_event

    from ai_detector_core.events.transport import EventMessage, SnapshotMetadata
    from ai_detector_core.storage.snapshots import snapshot_key
    from app.infrastructure.database.models import SnapshotModel

    redis, sessions, _ = transport
    original = await make_event(sessions)
    snapshot_id = uuid4()
    metadata = SnapshotMetadata(
        id=snapshot_id,
        event_id=original.id,
        storage_key=snapshot_key(original.camera_id, original.occurred_at, snapshot_id),
        width=10,
        height=20,
        size_bytes=4,
        created_at=datetime.now(UTC),
    )
    await EventPublisher(redis).publish(EventMessage(**original.model_dump(), snapshot=metadata))
    ingest = EventIngest(redis, sessions)
    batch = await read_batch(ingest)
    engine = sessions.kw["bind"]

    def fail_snapshot(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.startswith("INSERT INTO snapshots"):
            raise OSError("disk/connection failed while inserting snapshot")

    sql_event.listen(engine.sync_engine, "before_cursor_execute", fail_snapshot)
    try:
        with pytest.raises(OSError):
            await ingest.process(batch)
    finally:
        sql_event.remove(engine.sync_engine, "before_cursor_execute", fail_snapshot)
    async with sessions() as session:
        assert await session.get(EventModel, original.id) is None
        assert await session.get(SnapshotModel, snapshot_id) is None
    assert (await redis.xpending(INGEST_STREAM, INGEST_GROUP))["pending"] == 1
    await ingest.process(batch)
    async with sessions() as session:
        assert await session.get(EventModel, original.id)
        assert await session.get(SnapshotModel, snapshot_id)


async def test_expired_replay_does_not_resurrect_metadata_and_live_payload_is_private(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    from datetime import timedelta

    from ai_detector_core.events.transport import EventMessage, SnapshotMetadata
    from ai_detector_core.storage.snapshots import snapshot_key
    from ai_detector_core.telemetry.event_bus import EVENTS_LIVE
    from app.infrastructure.database.models import SnapshotModel

    redis, sessions, _ = transport
    original = await make_event(sessions)
    snapshot_id = uuid4()
    metadata = SnapshotMetadata(
        id=snapshot_id,
        event_id=original.id,
        storage_key=snapshot_key(original.camera_id, original.occurred_at, snapshot_id),
        width=10,
        height=20,
        size_bytes=4,
        created_at=datetime.now(UTC) - timedelta(days=31),
    )
    message = EventMessage(**original.model_dump(), snapshot=metadata)
    async with redis.pubsub() as pubsub:
        await pubsub.subscribe(EVENTS_LIVE)
        await pubsub.get_message(timeout=1)  # subscribe confirmation
        await EventPublisher(redis).publish(message)
        packet = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
        assert packet and b"storage_key" not in packet["data"] and b"snapshot" not in packet["data"]
    ingest = EventIngest(redis, sessions)
    batch = await read_batch(ingest)
    await ingest.process(batch)
    await ingest.process(batch)
    async with sessions() as session:
        assert await session.get(EventModel, original.id)
        assert await session.get(SnapshotModel, snapshot_id) is None


async def test_retention_lease_cannot_renew_or_release_another_owners_lock(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    from app.infrastructure.storage.snapshot_retention import LOCK, RELEASE, RENEW

    redis, _, _ = transport
    await redis.set(LOCK, "new-owner", ex=50)
    assert await redis.eval(RENEW, 1, LOCK, "old-owner") == 0
    assert await redis.eval(RELEASE, 1, LOCK, "old-owner") == 0
    assert await redis.get(LOCK) == b"new-owner"
    assert await redis.eval(RENEW, 1, LOCK, "new-owner") == 1
    assert await redis.ttl(LOCK) >= 119
    assert await redis.eval(RELEASE, 1, LOCK, "new-owner") == 1


async def test_line_event_snapshot_duplicate_operator_state_and_deleted_geometry(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
    tmp_path: Path,
) -> None:
    from ai_detector_core.events.domain import LineCrossMetadata
    from ai_detector_core.events.transport import EventMessage, SnapshotMetadata
    from ai_detector_core.storage.snapshots import LocalSnapshotStorage, snapshot_key
    from app.infrastructure.database.models import LineModel

    redis, sessions, configured = transport
    configured = configured.model_copy(update={"snapshot_path": tmp_path})
    base = await make_event(sessions)
    line_id, snapshot_id = uuid4(), uuid4()
    async with sessions() as session, session.begin():
        session.add(
            LineModel(
                id=line_id,
                camera_id=base.camera_id,
                name="Исходная",
                p1_x=0.2,
                p1_y=0.5,
                p2_x=0.8,
                p2_y=0.5,
                enabled=True,
            )
        )
    event = DomainEvent(
        **{
            **base.model_dump(),
            "type": "PERSON_CROSSED_LINE",
            "zone_id": None,
            "line_id": line_id,
            "severity": "warning",
            "metadata": LineCrossMetadata(
                bbox=(0.4, 0.2, 0.6, 0.7),
                anchor=(0.5, 0.7),
                stability=1,
                direction="LEFT_TO_RIGHT",
                line_name="Исходная",
                p1=(0.2, 0.5),
                p2=(0.8, 0.5),
            ),
        }
    )
    key = snapshot_key(base.camera_id, event.occurred_at, snapshot_id)
    storage = LocalSnapshotStorage(tmp_path)
    storage.put(key, b"\xff\xd8image")
    snapshot = SnapshotMetadata(
        id=snapshot_id,
        event_id=event.id,
        storage_key=key,
        width=100,
        height=100,
        size_bytes=7,
        created_at=datetime.now(UTC),
    )
    message = EventMessage(**event.model_dump(), snapshot=snapshot)
    publisher = EventPublisher(redis)
    ingest = EventIngest(redis, sessions)
    await publisher.publish(message)
    await publisher.publish(message)
    batch = await read_batch(ingest)
    await ingest.process(batch)
    app = create_app(configured)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        url = f"/api/v1/events/{event.id}"
        result = (await client.get(url)).json()
        assert (
            result["line_id"] == str(line_id)
            and result["zone_id"] is None
            and result["type"] == "PERSON_CROSSED_LINE"
        )
        assert result["metadata"]["direction"] == "LEFT_TO_RIGHT" and result["snapshot_id"] == str(
            snapshot_id
        )
        assert (await client.get(result["snapshot_url"])).status_code == 200
        assert (
            await client.patch(url, json={"status": "FALSE_POSITIVE", "note": "проверено"})
        ).status_code == 200
        linepath = f"/api/v1/cameras/{base.camera_id}/lines/{line_id}"
        assert (
            await client.put(
                linepath,
                json={"name": "Изменено", "p1": {"x": 0.1, "y": 0.1}, "p2": {"x": 0.9, "y": 0.9}},
            )
        ).status_code == 200
        assert (await client.delete(linepath)).status_code == 204
        result = (await client.get(url)).json()
        assert (
            result["line_id"] is None
            and result["metadata"]["line_name"] == "Исходная"
            and result["metadata"]["p1"] == [0.2, 0.5]
        )
        # Replay after FK deletion preserves history/operator state and does not restore FK.
        await ingest.process(batch)
        result = (await client.get(url)).json()
        assert (
            result["line_id"] is None
            and result["status"] == "FALSE_POSITIVE"
            and result["note"] == "проверено"
        )
        assert len((await client.get("/api/v1/events")).json()["items"]) == 1


async def test_cross_camera_line_reference_becomes_null_not_a_wrong_fk(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    from ai_detector_core.events.domain import LineCrossMetadata
    from app.infrastructure.database.models import LineModel

    redis, sessions, _ = transport
    first, other = await make_event(sessions), await make_event(sessions)
    line_id = uuid4()
    async with sessions() as session, session.begin():
        session.add(
            LineModel(
                id=line_id,
                camera_id=other.camera_id,
                name="other",
                p1_x=0,
                p1_y=0,
                p2_x=1,
                p2_y=1,
                enabled=True,
            )
        )
    event = DomainEvent(
        **{
            **first.model_dump(),
            "type": "PERSON_CROSSED_LINE",
            "zone_id": None,
            "line_id": line_id,
            "metadata": LineCrossMetadata(
                bbox=(0, 0, 1, 1),
                anchor=(0.5, 0.5),
                stability=1,
                direction="RIGHT_TO_LEFT",
                line_name="other",
                p1=(0, 0),
                p2=(1, 1),
            ),
        }
    )
    await EventPublisher(redis).publish(event)
    ingest = EventIngest(redis, sessions)
    await ingest.process(await read_batch(ingest))
    async with sessions() as session:
        saved = await session.get(EventModel, event.id)
        assert saved and saved.line_id is None and saved.type == "PERSON_CROSSED_LINE"


async def test_loitering_transport_roundtrip_duplicate_operator_state(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    from ai_detector_core.events.domain import LoiteringMetadata

    redis, sessions, settings = transport
    base = await make_event(sessions)
    event = DomainEvent.model_validate(
        {
            **base.model_dump(),
            "type": "PERSON_LOITERING_IN_DANGER_ZONE",
            "severity": "warning",
            "metadata": LoiteringMetadata(
                bbox=(0.1, 0.1, 0.5, 0.5),
                anchor=(0.3, 0.5),
                stability=1,
                zone_name="Зона",
                duration_seconds=10.1,
                threshold_seconds=10,
            ),
        }
    )
    ingest = EventIngest(redis, sessions)
    publisher = EventPublisher(redis)
    await publisher.publish(event)
    await ingest.process(await read_batch(ingest))
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get(f"/api/v1/events/{event.id}")
        assert response.status_code == 200
        assert response.json()["metadata"]["duration_seconds"] == 10.1
        assert (
            await client.patch(
                f"/api/v1/events/{event.id}", json={"status": "FALSE_POSITIVE", "note": "Заметка"}
            )
        ).status_code == 200
        await publisher.publish(event)
        await ingest.process(await read_batch(ingest))
        row = (await client.get(f"/api/v1/events/{event.id}")).json()
        assert row["status"] == "FALSE_POSITIVE" and row["note"] == "Заметка"


async def test_csv_complete_filters_boundaries_archived_formula_and_empty(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    import csv
    import io
    from datetime import timedelta

    from sqlalchemy import update

    redis, sessions, settings = transport
    event = await make_event(sessions)
    async with sessions() as session, session.begin():
        await session.execute(
            update(CameraModel)
            .where(CameraModel.id == event.camera_id)
            .values(name="=1+1", deleted_at=datetime.now(UTC))
        )
    ingest = EventIngest(redis, sessions)
    events = [event.model_copy(update={"id": uuid4()}) for _ in range(71)]
    events.append(
        event.model_copy(
            update={"id": uuid4(), "occurred_at": event.occurred_at + timedelta(seconds=1)}
        )
    )
    await ingest.process(
        [(str(i).encode(), {b"event": e.model_dump_json().encode()}) for i, e in enumerate(events)]
    )
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        first = events[0]
        await client.patch(
            f"/api/v1/events/{first.id}",
            json={"status": "FALSE_POSITIVE", "note": ' =1+1\n"Заметка",да'},
        )
        params = {
            "camera_id": str(event.camera_id),
            "event_type": event.type,
            "start": event.occurred_at.isoformat(),
            "end": (event.occurred_at + timedelta(seconds=1)).isoformat(),
        }
        history = (await client.get("/api/v1/events", params=params)).json()
        assert len(history["items"]) == 50 and history["next_cursor"]
        result = await client.get("/api/v1/events/export", params=params)
        assert (
            result.status_code == 200
            and result.headers["content-type"] == "text/csv; charset=utf-8"
        )
        assert (
            "attachment" in result.headers["content-disposition"]
            and result.headers["cache-control"] == "private, no-store"
        )
        rows = list(csv.DictReader(io.StringIO(result.content.decode("utf-8-sig"), newline="")))
        assert len(rows) == 71 and {r["id"] for r in rows} == {str(e.id) for e in events[:-1]}
        assert all(r["camera_name"] == "'=1+1" for r in rows)
        assert next(r for r in rows if r["id"] == str(first.id))["note"].startswith("' =1+1")
        assert "storage_key" not in result.text
        fp = await client.get(
            "/api/v1/events/export", params={**params, "status": "FALSE_POSITIVE"}
        )
        assert len(list(csv.DictReader(io.StringIO(fp.content.decode("utf-8-sig"))))) == 1
        empty = await client.get(
            "/api/v1/events/export", params={**params, "event_type": "PERSON_CROSSED_LINE"}
        )
        assert len(list(csv.DictReader(io.StringIO(empty.content.decode("utf-8-sig"))))) == 0
        for bad in (
            {"start": "2026-01-01"},
            {"event_type": "other"},
            {"status": "other"},
            {"start": params["end"], "end": params["start"]},
        ):
            assert (await client.get("/api/v1/events/export", params=bad)).status_code == 422


async def test_csv_oversize_and_database_failure_are_json_not_partial_download(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.application import event_export, event_service
    from app.infrastructure.database.repositories.events import EventRepository

    redis, sessions, settings = transport
    event = await make_event(sessions)
    ingest = EventIngest(redis, sessions)
    await ingest.process([(b"1-0", {b"event": event.model_dump_json().encode()})])
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        monkeypatch.setattr(event_export, "MAX_EXPORT_ROWS", 0)
        monkeypatch.setattr(event_service, "MAX_EXPORT_ROWS", 0)
        response = await client.get("/api/v1/events/export")
        assert (
            response.status_code == 422 and response.json()["error"]["code"] == "EXPORT_TOO_LARGE"
        )
        assert "content-disposition" not in response.headers

        async def fail(*args: object, **kwargs: object) -> None:
            raise OperationalError("SELECT", {}, Exception("offline"))

        monkeypatch.setattr(EventRepository, "export_rows", fail)
        response = await client.get("/api/v1/events/export")
        assert response.status_code == 503
        assert response.headers["content-type"] == "application/json"


async def test_csv_concurrency_limit_is_503_without_partial_attachment(
    transport: tuple[Redis, async_sessionmaker[AsyncSession], Settings],
) -> None:
    _, _, settings = transport
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        slots = app.state.resources.csv_export_slots
        await slots.acquire()
        await slots.acquire()
        try:
            response = await client.get("/api/v1/events/export")
            assert response.status_code == 503
            assert "content-disposition" not in response.headers
        finally:
            slots.release()
            slots.release()
        assert (await client.get("/api/v1/events/export")).status_code == 200
