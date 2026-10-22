"""Real PostgreSQL/Valkey: delivery, replay, poison messages, REST and live fanout."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
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
        await conn.execute(text("TRUNCATE events, zones, camera_configs, cameras CASCADE"))
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
