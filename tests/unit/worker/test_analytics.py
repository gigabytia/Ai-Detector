"""Deterministic analytics lifecycle and bounded observations."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from worker_fakes import make_frame

from ai_detector_core.people.track import PersonState, PersonTrack
from ai_detector_core.telemetry.analytics import (
    ANALYTICS_ADAPTER,
    CameraSample,
    Segment,
    TrackSession,
)
from vision_worker.pipeline.analytics import AnalyticsCollector
from vision_worker.pipeline.results import DetectionResult

AT = datetime(2026, 1, 1, tzinfo=UTC)
CID, RID = uuid4(), uuid4()


class Sink:
    def __init__(self) -> None:
        self.messages: list[CameraSample | TrackSession] = []

    def offer(self, message: CameraSample | TrackSession) -> None:
        self.messages.append(message)


def result(
    seconds: float, state: PersonState = PersonState.NORMAL, *, empty: bool = False
) -> DetectionResult:
    at = AT + timedelta(seconds=seconds)
    frame = replace(make_frame(0, 100, 100), captured_at=at)
    track = PersonTrack(1, CID, RID, (0, 0, 20, 30), 0.8, AT, at, 0, seconds * 1000, 3, 3, 0, state)
    return DetectionResult(CID, RID, frame, (), 0, tracks=() if empty else (track,))


def collector() -> tuple[AnalyticsCollector, Sink]:
    from typing import cast

    from vision_worker.messaging.analytics import AnalyticsPublisher

    sink = Sink()
    return AnalyticsCollector(cast(AnalyticsPublisher, sink)), sink


def test_one_sample_per_observed_second_latest_and_final_flush() -> None:
    c, s = collector()
    for t in [0, 0.2, 0.9, 1.1, 1.3]:
        c.offer(result(t))
    assert len(s.messages) == 1
    assert isinstance(s.messages[0], CameraSample)
    assert s.messages[0].at == AT + timedelta(seconds=0.9)
    c.retain(set())
    samples = [m for m in s.messages if isinstance(m, CameraSample)]
    assert len(samples) == 2 and len({m.id for m in samples}) == 2
    assert sum(m.observed_seconds for m in samples) == pytest.approx(1.3)
    assert not c.tracks and not c.samples and not c.last


def test_final_track_segments_include_lost_and_zone() -> None:
    c, s = collector()
    c.offer(result(0))
    c.offer(result(1, PersonState.IN_DANGER_ZONE))
    c.offer(result(2, PersonState.LOST))
    c.offer(result(3, empty=True))
    tracks = [m for m in s.messages if isinstance(m, TrackSession)]
    assert len(tracks) == 1 and tracks[0].track_id == 1
    assert [p.state for p in tracks[0].segments] == ["NORMAL", "IN_DANGER_ZONE", "LOST"]
    assert tracks[0].ended_at == AT + timedelta(seconds=2)
    c.retain(set())
    assert len([m for m in s.messages if isinstance(m, TrackSession)]) == 1


def test_gaps_not_filled_with_zero_and_no_observation_duration_extrapolation() -> None:
    c, s = collector()
    c.offer(result(0))
    c.offer(result(10))
    c.retain(set())
    samples = [m for m in s.messages if isinstance(m, CameraSample)]
    assert len(samples) == 2 and all(m.observed_seconds == 0 for m in samples)


def test_run_isolation_and_stable_id_for_replay() -> None:
    a, s = collector()
    b, t = collector()
    for c in [a, b]:
        c.offer(result(0))
        c.retain(set())
    assert [m.id for m in s.messages] == [m.id for m in t.messages]
    c, _ = collector()
    c.offer(result(0))
    c.offer(replace(result(1), run_id=uuid4()))
    assert len(c.samples) == 2


def test_out_of_order_frame_does_not_rewind_state() -> None:
    c, s = collector()
    c.offer(result(2))
    c.offer(result(1))
    c.retain(set())
    assert all(m.at == AT + timedelta(seconds=2) for m in s.messages if isinstance(m, CameraSample))


def test_segment_bound_is_explicit_not_unbounded() -> None:
    c, s = collector()
    for i in range(2055):
        c.offer(result(i / 100, PersonState.NORMAL if i % 2 else PersonState.LOST))
    c.retain(set())
    t = next(m for m in s.messages if isinstance(m, TrackSession))
    assert len(t.segments) == 2048 and t.truncated


@pytest.mark.parametrize(
    "changes",
    [
        {"persons": -1},
        {"observed_seconds": float("nan")},
        {"version": 2},
        {"at": "2026-01-01T00:00:00"},
    ],
)
def test_transport_rejects_invalid_sample(changes: dict[str, object]) -> None:
    payload = CameraSample(
        id=uuid4(),
        camera_id=CID,
        run_id=RID,
        at=AT,
        persons=0,
        persons_in_zone=0,
        observed_seconds=0,
    ).model_dump()
    with pytest.raises(ValidationError):
        ANALYTICS_ADAPTER.validate_python({**payload, **changes})


def test_transport_rejects_unordered_segments() -> None:
    with pytest.raises(ValidationError):
        Segment(state="NORMAL", start=AT, end=AT - timedelta(seconds=1))
    with pytest.raises(ValidationError):
        TrackSession(
            id=uuid4(),
            camera_id=CID,
            run_id=RID,
            track_id=1,
            started_at=AT,
            ended_at=AT,
            segments=(Segment(state="NORMAL", start=AT, end=AT + timedelta(seconds=1)),),
        )


def test_long_unobserved_gap_is_not_drawn_as_continuous_normal() -> None:
    c, s = collector()
    c.offer(result(0))
    c.offer(result(10))
    c.retain(set())
    track = next(m for m in s.messages if isinstance(m, TrackSession))
    assert any(
        p.state == "LOST" and (p.end - p.start).total_seconds() == 10 for p in track.segments
    )


async def test_analytics_outbox_is_bounded_and_does_not_use_alarm_queue() -> None:
    from typing import cast
    from unittest.mock import AsyncMock

    from redis.asyncio import Redis

    from vision_worker.messaging.analytics import AnalyticsPublisher

    client = AsyncMock()
    publisher = AnalyticsPublisher(cast(Redis, client), capacity=1)
    sample = CameraSample(
        id=uuid4(),
        camera_id=CID,
        run_id=RID,
        at=AT,
        persons=0,
        persons_in_zone=0,
        observed_seconds=0,
    )
    publisher.offer(sample)
    publisher.offer(sample)
    assert publisher.dropped == 1 and not publisher.healthy and publisher.queue.qsize() == 1
    await publisher.publish(sample)
    assert client.xadd.call_args.args[0] == "ad:analytics:ingest"
    client.publish.assert_not_called()


def test_fractional_bucket_boundary_does_not_clip_observed_duration() -> None:
    c, s = collector()
    for t in [0.9, 2.8, 2.99]:
        c.offer(result(t))
    c.retain(set())
    assert sum(
        m.observed_seconds for m in s.messages if isinstance(m, CameraSample)
    ) == pytest.approx(2.09)
