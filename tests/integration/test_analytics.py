"""Real database aggregations, overlap/pagination, transport retry and no-data semantics."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_detector_core.telemetry.analytics import (
    ANALYTICS_STREAM,
    CameraSample,
    Segment,
    TrackSession,
)
from app.core.config import Settings
from app.infrastructure.database.models import (
    CameraModel,
    CameraSampleModel,
    EventModel,
    TrackSessionModel,
)
from app.infrastructure.redis.analytics import AnalyticsIngest
from app.infrastructure.redis.ingest import stream_messages
from app.main import create_app
from vision_worker.messaging.analytics import AnalyticsPublisher

pytestmark = pytest.mark.integration
AT = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
async def database(
    settings: Settings,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], Settings]]:
    engine = create_async_engine(str(settings.database_url))
    async with engine.begin() as c:
        await c.execute(text("TRUNCATE cameras CASCADE"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    yield sessions, settings
    await engine.dispose()


async def seed(sessions: async_sessionmaker[AsyncSession]) -> tuple[object, object]:
    cid, other = uuid4(), uuid4()
    run = uuid4()
    async with sessions() as s, s.begin():
        s.add_all(
            [
                CameraModel(
                    id=cid,
                    name="Камера A",
                    source_type="mock",
                    source_url="mock://walk_through",
                    enabled=True,
                ),
                CameraModel(
                    id=other,
                    name="Архив B",
                    source_type="mock",
                    source_url="mock://walk_through",
                    enabled=False,
                    deleted_at=AT,
                ),
            ]
        )
        await s.flush()
        for camera, sec, severity, status, kind in [
            (cid, 0, "critical", "NEW", "PERSON_ENTERED_DANGER_ZONE"),
            (cid, 30, "warning", "FALSE_POSITIVE", "PERSON_CROSSED_LINE"),
            (other, 59, "critical", "ACKNOWLEDGED", "PERSON_ENTERED_DANGER_ZONE"),
            (cid, 60, "warning", "NEW", "PERSON_CROSSED_LINE"),
        ]:
            s.add(
                EventModel(
                    id=uuid4(),
                    camera_id=camera,
                    run_id=run,
                    track_id=1,
                    type=kind,
                    severity=severity,
                    status=status,
                    occurred_at=AT + timedelta(seconds=sec),
                    source_ts_ms=0,
                    detector_confidence=0.8,
                    event_confidence=0.7,
                    message="test",
                    event_metadata={},
                )
            )
        for sec, persons in [(0, 0), (1, 4), (10, 2)]:
            s.add(
                CameraSampleModel(
                    id=uuid4(),
                    camera_id=cid,
                    run_id=run,
                    at=AT + timedelta(seconds=sec),
                    persons=persons,
                    persons_in_zone=0,
                    observed_seconds=0.8,
                )
            )
        for i in range(3):
            s.add(
                TrackSessionModel(
                    id=uuid4(),
                    camera_id=cid,
                    run_id=run,
                    track_id=i + 1,
                    started_at=AT - timedelta(seconds=5),
                    ended_at=AT + timedelta(seconds=20),
                    segments=[
                        Segment(
                            state="NORMAL",
                            start=AT - timedelta(seconds=5),
                            end=AT + timedelta(seconds=20),
                        ).model_dump(mode="json")
                    ],
                    truncated=False,
                )
            )
    return cid, other


def params() -> dict[str, str]:
    return {"start": AT.isoformat(), "end": (AT + timedelta(seconds=60)).isoformat()}


async def test_dashboard_counts_crossfoot_boundaries_archive_and_missing_samples(
    database: tuple[async_sessionmaker[AsyncSession], Settings],
) -> None:
    sessions, settings = database
    cid, other = await seed(sessions)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings)), base_url="http://test"
    ) as c:
        # ASGITransport doesn't run lifespan; explicitly install real request resources.
        from app.core.lifecycle import build_resources, close_resources

        app = c._transport.app  # type: ignore[attr-defined]
        resources = build_resources(settings)
        app.state.resources = resources
        try:
            r = await c.get("/api/v1/analytics", params=params())
            assert r.status_code == 200, r.text
            x = r.json()
            assert (
                x["total_events"] == 3 and x["critical_events"] == 2 and x["false_positives"] == 1
            )
            assert x["average_events_per_camera"] == 1.5 and x["enabled_cameras"] == 1
            assert sum(b["events"] for b in x["events_over_time"]) == 3
            assert sum(b["count"] for b in x["by_type"]) == 3
            archived = next(b for b in x["by_camera"] if b["camera_id"] == str(other))
            assert archived["archived"] and archived["average_persons"] is None
            first = next(b for b in x["by_camera"] if b["camera_id"] == str(cid))
            assert (
                first["average_persons"] == 2
                and first["max_persons"] == 4
                and first["observed_seconds"] == pytest.approx(2.4)
            )
            selected = (
                await c.get("/api/v1/analytics", params={**params(), "camera_id": str(cid)})
            ).json()
            assert selected["total_events"] == 2 and len(selected["people_over_time"]) == 3
            assert x["people_over_time"] == [] and selected["completed_tracks"] == 3
            offset = (
                await c.get(
                    "/api/v1/analytics",
                    params={
                        "start": "2026-01-01T03:00:00+03:00",
                        "end": "2026-01-01T03:01:00+03:00",
                        "camera_id": str(cid),
                    },
                )
            ).json()
            assert offset["events_over_time"] == selected["events_over_time"]
            assert offset["people_over_time"] == selected["people_over_time"]

        finally:
            await close_resources(resources)


async def test_track_overlap_keyset_ties_and_no_duplicates(
    database: tuple[async_sessionmaker[AsyncSession], Settings],
) -> None:
    sessions, _ = database
    cid, _ = await seed(sessions)
    from app.infrastructure.database.repositories.analytics import AnalyticsRepository

    async with sessions() as s:
        repo = AnalyticsRepository(s)
        one = await repo.tracks(AT, AT + timedelta(seconds=60), None, 2, None)
        two = await repo.tracks(AT, AT + timedelta(seconds=60), None, 2, one.next_cursor)
        assert len(one.items) == 2 and len(two.items) == 1 and not two.next_cursor
        assert len({t.id for t in one.items + two.items}) == 3
        assert all(t.camera_id == cid and t.started_at < AT for t in one.items + two.items)


async def test_analytics_replay_poison_and_commit_before_ack(
    database: tuple[async_sessionmaker[AsyncSession], Settings],
) -> None:
    sessions, settings = database
    cid, _ = await seed(sessions)
    from uuid import UUID

    camera = UUID(str(cid))
    redis = Redis.from_url(str(settings.redis_url).rsplit("/", 1)[0] + "/12")
    await redis.flushdb()
    try:
        publisher = AnalyticsPublisher(redis)
        ingest = AnalyticsIngest(redis, sessions)
        sample = CameraSample(
            id=uuid4(),
            camera_id=camera,
            run_id=uuid4(),
            at=AT,
            persons=1,
            persons_in_zone=0,
            observed_seconds=0.5,
        )
        track = TrackSession(
            id=uuid4(),
            camera_id=camera,
            run_id=sample.run_id,
            track_id=50,
            started_at=AT,
            ended_at=AT + timedelta(seconds=1),
            segments=(Segment(state="NORMAL", start=AT, end=AT + timedelta(seconds=1)),),
        )
        payloads: list[CameraSample | TrackSession] = [sample, sample, track, track]
        for message in payloads:
            await publisher.publish(message)
        await redis.xadd(ANALYTICS_STREAM, {"data": "bad"})
        await ingest.ensure_group()
        messages = stream_messages(
            await redis.xreadgroup(ingest.group, ingest.consumer, {ingest.stream: ">"}, count=20)
        )
        await ingest.process(messages)
        assert await redis.xlen(ANALYTICS_STREAM) == 0 and await redis.xlen(ingest.dead) == 1
        async with sessions() as s:
            assert await s.get(CameraSampleModel, sample.id)
            assert await s.get(TrackSessionModel, track.id)
        await publisher.publish(sample)
        messages = stream_messages(
            await redis.xreadgroup(ingest.group, ingest.consumer, {ingest.stream: ">"}, count=20)
        )
        from unittest.mock import patch

        from sqlalchemy.exc import OperationalError

        with (
            patch.object(
                ingest, "sessions", side_effect=OperationalError("db", {}, Exception("down"))
            ),
            pytest.raises(OperationalError),
        ):
            await ingest.process(messages)
        assert await redis.xlen(ingest.stream) == 1
        await ingest.process(messages)
        assert await redis.xlen(ingest.stream) == 0
    finally:
        await redis.flushdb()
        await redis.aclose()


async def test_empty_dashboard_and_window_validation(
    database: tuple[async_sessionmaker[AsyncSession], Settings],
) -> None:
    _, settings = database
    from app.core.lifecycle import build_resources, close_resources

    app = create_app(settings)
    resources = build_resources(settings)
    app.state.resources = resources
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        try:
            x = (await c.get("/api/v1/analytics", params=params())).json()
            assert (
                x["total_events"] == 0
                and x["average_events_per_camera"] is None
                and not x["by_camera"]
            )
            for p in [
                {"start": "2026-01-01", "end": "2026-02-03"},
                {"start": AT.isoformat(), "end": AT.isoformat()},
                {"start": "2026-01-01T00:00:00"},
                {"start": "garbage"},
            ]:
                assert (await c.get("/api/v1/analytics", params=p)).status_code == 422
            assert (
                await c.get("/api/v1/analytics/tracks", params={"cursor": "broken"})
            ).status_code == 422
        finally:
            await close_resources(resources)
