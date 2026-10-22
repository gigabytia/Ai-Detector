"""Deterministic membership, timing, confidence, resets and cooldown."""

from dataclasses import replace
from uuid import uuid4

import pytest
from worker_fakes import make_frame

from ai_detector_core.cameras.config import CameraConfig
from ai_detector_core.events.domain import DomainEvent, LoiteringMetadata
from ai_detector_core.people.track import PersonState, PersonTrack
from ai_detector_core.zones.model import ZoneSpec
from fakes import FixedClock
from vision_worker.pipeline.results import DetectionResult
from vision_worker.rules.registry import SceneRegistry
from vision_worker.rules.zone_engine import ZoneEngine

CID, RID, ZID = uuid4(), uuid4(), uuid4()
ZONE = ZoneSpec(
    id=ZID,
    camera_id=CID,
    name="Опасная зона",
    points=[{"x": 0.2, "y": 0.2}, {"x": 0.8, "y": 0.2}, {"x": 0.8, "y": 0.9}, {"x": 0.2, "y": 0.9}],
)


def track(inside: bool = True, lost: bool = False, hits: int = 10, tid: int = 1) -> PersonTrack:
    frame = make_frame(0, 100, 100)
    return PersonTrack(
        tid,
        CID,
        RID,
        (30, 10, 50, 80) if inside else (0, 0, 10, 10),
        0.8,
        frame.captured_at,
        frame.captured_at,
        0,
        0,
        10,
        hits,
        1 if lost else 0,
        PersonState.LOST if lost else PersonState.NORMAL,
    )


def tick(
    engine: ZoneEngine,
    ms: float,
    *,
    inside: bool = True,
    lost: bool = False,
    hits: int = 10,
    config: CameraConfig | None = None,
    zones: tuple[ZoneSpec, ...] = (ZONE,),
) -> tuple[tuple[PersonTrack, ...], tuple[DomainEvent, ...]]:
    return engine.update(
        replace(make_frame(int(ms), 100, 100), source_ts_ms=ms),
        (track(inside, lost, hits),),
        zones,
        config or CameraConfig(),
    )


def test_dwell_confirmed_once_and_metadata_uses_anchor() -> None:
    engine = ZoneEngine(FixedClock())
    assert not tick(engine, 0)[1]
    assert not tick(engine, 249)[1]
    tracks, events = tick(engine, 250)
    assert tracks[0].state == PersonState.IN_DANGER_ZONE and len(events) == 1
    event = events[0]
    assert (
        event.type == "PERSON_ENTERED_DANGER_ZONE" and event.zone_id == ZID and event.run_id == RID
    )
    assert event.metadata.anchor == (0.4, 0.8) and event.metadata.bbox == (0.3, 0.1, 0.5, 0.8)
    assert event.event_confidence == pytest.approx(0.8) and event.metadata.stability == 1
    assert event.occurred_at.tzinfo is not None
    assert not tick(engine, 10000)[1]


def test_short_entry_and_minimum_hits_do_not_trigger() -> None:
    engine = ZoneEngine(FixedClock())
    tick(engine, 0)
    assert not tick(engine, 100, inside=False)[1]
    tick(engine, 200, hits=1)
    assert not tick(engine, 500, hits=2)[1]
    assert len(tick(engine, 600, hits=3)[1]) == 1


def test_exit_grace_suppresses_jitter_then_allows_next_visit() -> None:
    clock = FixedClock()
    engine = ZoneEngine(clock)
    tick(engine, 0)
    tick(engine, 300)
    assert tick(engine, 400, inside=False)[0][0].state == PersonState.IN_DANGER_ZONE
    assert not tick(engine, 700)[1]
    tick(engine, 800, inside=False)
    assert tick(engine, 1300, inside=False)[0][0].state == PersonState.NORMAL
    clock.advance(4)
    tick(engine, 1400)
    assert len(tick(engine, 1700)[1]) == 1


def test_cooldown_is_wall_clock_and_suppressed_entry_is_not_retried_inside() -> None:
    clock = FixedClock()
    engine = ZoneEngine(clock)
    tick(engine, 0)
    tick(engine, 300)
    tick(engine, 400, inside=False)
    tick(engine, 900, inside=False)
    tick(engine, 1000)
    assert not tick(engine, 1300)[1]
    clock.advance(5)
    assert not tick(engine, 9000)[1]
    tick(engine, 9100, inside=False)
    tick(engine, 9600, inside=False)
    tick(engine, 9700)
    assert tick(engine, 10000)[1]


def test_lost_freezes_dwell_and_penalizes_confidence() -> None:
    engine = ZoneEngine(FixedClock())
    tick(engine, 0)
    tick(engine, 100)
    assert tick(engine, 1000, lost=True)[0][0].state == PersonState.LOST
    tick(engine, 2000, lost=True)
    assert not tick(engine, 3000)[1]  # the lost gap cannot complete dwell
    events = tick(engine, 3150)[1]
    assert len(events) == 1
    assert events[0].metadata.stability == pytest.approx(4 / 6)
    assert events[0].event_confidence == pytest.approx(0.8 * 4 / 6)


def test_lost_freezes_exit_grace() -> None:
    engine = ZoneEngine(FixedClock())
    tick(engine, 0)
    tick(engine, 300)
    tick(engine, 400, inside=False)
    tick(engine, 1000, lost=True)
    assert tick(engine, 3000, inside=False)[0][0].state == PersonState.IN_DANGER_ZONE
    assert tick(engine, 3500, inside=False)[0][0].state == PersonState.NORMAL


def test_deleted_disabled_changed_zone_clears_membership_without_old_entry() -> None:
    engine = ZoneEngine(FixedClock())
    tick(engine, 0)
    tick(engine, 300)
    assert tick(engine, 400, zones=())[0][0].state == PersonState.NORMAL
    assert not engine._visits
    assert (
        tick(engine, 500, zones=(ZONE.model_copy(update={"enabled": False}),))[0][0].state
        == PersonState.NORMAL
    )
    tick(engine, 600)
    moved = ZONE.model_copy(
        update={"points": tuple(p.model_copy(update={"x": p.x / 10}) for p in ZONE.points)}
    )
    assert tick(engine, 1000, zones=(moved,))[0][0].state == PersonState.NORMAL


def test_removed_tracks_release_visits_and_cooldown() -> None:
    engine = ZoneEngine(FixedClock())
    tick(engine, 0)
    tick(engine, 300)
    engine.update(make_frame(4, 100, 100), (), (ZONE,), CameraConfig())
    assert not engine._visits and not engine._cooldown


def test_multiple_zones_share_camera_track_type_cooldown() -> None:
    engine = ZoneEngine(FixedClock())
    zones = (ZONE, ZONE.model_copy(update={"id": uuid4()}))
    tick(engine, 0, zones=zones)
    tracks, events = tick(engine, 300, zones=zones)
    assert tracks[0].state == PersonState.IN_DANGER_ZONE and len(events) == 1


def test_zero_thresholds_and_hot_config() -> None:
    engine = ZoneEngine(FixedClock(), min_hits=1)
    config = CameraConfig(
        zone_enter_dwell_seconds=0, zone_exit_grace_seconds=0, event_cooldown_seconds=0
    )
    assert tick(engine, 0, config=config)[1]
    assert tick(engine, 1, inside=False, config=config)[0][0].state == PersonState.NORMAL
    assert tick(engine, 2, config=config)[1]


def test_scene_epoch_resets_membership_and_retention_cleans_runs() -> None:
    scenes = SceneRegistry(FixedClock(), min_hits=1)

    def result(ms: int, epoch: int = 0) -> DetectionResult:
        return DetectionResult(
            CID,
            RID,
            replace(make_frame(ms, 100, 100), source_ts_ms=ms, source_epoch=epoch),
            (),
            0,
            (track(),),
            (ZONE,),
        )

    scenes.update(result(0), CameraConfig())
    assert scenes.update(result(300), CameraConfig()).events
    assert not scenes.update(result(400, 1), CameraConfig()).events
    scenes.retain(set())
    assert not scenes._entries


def test_changed_geometry_does_not_reset_another_zone_or_rename_membership() -> None:
    engine = ZoneEngine(FixedClock())
    other = ZONE.model_copy(update={"id": uuid4()})
    tick(engine, 0, zones=(ZONE, other))
    tick(engine, 300, zones=(ZONE, other))
    moved = ZONE.model_copy(
        update={"points": tuple(p.model_copy(update={"x": p.x / 10}) for p in ZONE.points)}
    )
    renamed = other.model_copy(update={"name": "Другое имя"})
    tracks, events = tick(engine, 400, zones=(moved, renamed))
    assert tracks[0].state == PersonState.IN_DANGER_ZONE and not events
    assert engine._visits[(1, other.id)].phase == "INSIDE"
    assert engine._visits[(1, ZONE.id)].phase == "OUTSIDE"


def test_dwell_override_applies_to_existing_entry_without_reset() -> None:
    engine = ZoneEngine(FixedClock())
    tick(engine, 0, config=CameraConfig(zone_enter_dwell_seconds=2))
    assert not tick(engine, 300, config=CameraConfig(zone_enter_dwell_seconds=2))[1]
    assert len(tick(engine, 400, config=CameraConfig(zone_enter_dwell_seconds=0.25))[1]) == 1


def test_resolution_and_discontinuity_reset_scene_and_keep_severity() -> None:
    scenes = SceneRegistry(FixedClock(), severity="warning")
    config = CameraConfig()
    result = DetectionResult(CID, RID, make_frame(0, 100, 100), (), 0, (track(),), (ZONE,))
    scenes.update(result, config)
    event = scenes.update(replace(result, frame=make_frame(10, 100, 100)), config).events[0]
    assert event.severity == "warning"
    changed = replace(result, frame=make_frame(11, 200, 100))
    assert not scenes.update(changed, config).events
    assert scenes.update(replace(changed, frame=make_frame(20, 200, 100)), config).events
    reset = replace(changed, frame=replace(make_frame(21, 200, 100), discontinuity=True))
    assert not scenes.update(reset, config).events


def loiter_events(events: tuple[DomainEvent, ...]) -> list[DomainEvent]:
    return [e for e in events if e.type == "PERSON_LOITERING_IN_DANGER_ZONE"]


def test_loitering_strict_threshold_source_time_one_event_not_wall_clock() -> None:
    clock = FixedClock()
    engine = ZoneEngine(clock)
    for ms in range(0, 10001, 1000):
        clock.advance(99)
        assert not loiter_events(tick(engine, ms)[1])
    event = loiter_events(tick(engine, 10001)[1])[0]
    assert isinstance(event.metadata, LoiteringMetadata)
    assert event.severity == "warning" and event.metadata.duration_seconds == pytest.approx(10.001)
    assert event.metadata.threshold_seconds == 10 and event.metadata.zone_name == ZONE.name
    assert DomainEvent.model_validate_json(event.model_dump_json()) == event
    for ms in range(11000, 30000, 1000):
        assert not loiter_events(tick(engine, ms)[1])


def test_loitering_lost_and_observed_outside_reset_unfired_clock() -> None:
    engine = ZoneEngine(FixedClock())
    config = CameraConfig(loitering_threshold_seconds=2)
    tick(engine, 0, config=config)
    tick(engine, 1000, config=config)
    assert not loiter_events(tick(engine, 2000, lost=True, config=config)[1])
    for ms in (3000, 4000, 5000):
        assert not loiter_events(tick(engine, ms, config=config)[1])
    assert len(loiter_events(tick(engine, 5001, config=config)[1])) == 1
    # Brief outside/LOST after firing must not re-arm the SAME confirmed visit.
    tick(engine, 5100, inside=False, config=config)
    tick(engine, 5200, config=config)
    tick(engine, 5300, lost=True, config=config)
    for ms in (5400, 6400, 7400, 8400):
        assert not loiter_events(tick(engine, ms, config=config)[1])


def test_confirmed_exit_allows_second_loitering_without_entry_cooldown_collision() -> None:
    clock = FixedClock()
    engine = ZoneEngine(clock)
    config = CameraConfig(loitering_threshold_seconds=1)
    tick(engine, 0, config=config)
    tick(engine, 500, config=config)
    assert len(loiter_events(tick(engine, 1001, config=config)[1])) == 1
    tick(engine, 1100, inside=False, config=config)
    tick(engine, 1700, inside=False, config=config)
    clock.advance(4)
    tick(engine, 1800, config=config)
    tick(engine, 2300, config=config)
    assert len(loiter_events(tick(engine, 2801, config=config)[1])) == 1


@pytest.mark.parametrize("gap", [3000, -100])
def test_loitering_clock_reset_on_capture_gap_or_backward_source_time(gap: int) -> None:
    engine = ZoneEngine(FixedClock())
    config = CameraConfig(loitering_threshold_seconds=1)
    tick(engine, 0, config=config)
    tick(engine, 500, config=config)
    assert not loiter_events(tick(engine, gap, config=config)[1])
    assert not loiter_events(tick(engine, gap + 500, config=config)[1])
    assert len(loiter_events(tick(engine, gap + 1001, config=config)[1])) == 1


def test_hot_threshold_preserves_visit_and_fired_marker_and_severity() -> None:
    engine = ZoneEngine(FixedClock(), loitering_severity="critical")
    for ms in (0, 500, 1000):
        tick(engine, ms)
    config = CameraConfig(loitering_threshold_seconds=0.5)
    event = loiter_events(tick(engine, 1100, config=config)[1])[0]
    assert event.severity == "critical"
    assert not loiter_events(
        tick(engine, 1200, config=CameraConfig(loitering_threshold_seconds=0))[1]
    )


def test_geometry_disable_removal_and_multiple_zone_membership() -> None:
    engine = ZoneEngine(FixedClock())
    config = CameraConfig(loitering_threshold_seconds=0.5, event_cooldown_seconds=0)
    other = ZONE.model_copy(update={"id": uuid4()})
    tick(engine, 0, config=config, zones=(ZONE, other))
    events = loiter_events(tick(engine, 600, config=config, zones=(ZONE, other))[1])
    assert {e.zone_id for e in events} == {ZONE.id, other.id}
    tick(engine, 700, config=config, zones=())
    tick(engine, 800, config=config, zones=(ZONE,))
    assert len(loiter_events(tick(engine, 1400, config=config, zones=(ZONE,))[1])) == 1
    engine.update(make_frame(1500, 100, 100), (), (ZONE,), config)
    tick(engine, 1600, config=config)
    assert len(loiter_events(tick(engine, 2200, config=config)[1])) == 1


def test_loitering_scene_reset_does_not_inherit_previous_timer() -> None:
    scenes = SceneRegistry(FixedClock())
    config = CameraConfig(loitering_threshold_seconds=1)
    base = DetectionResult(CID, RID, make_frame(0, 100, 100), (), 0, (track(),), (ZONE,))
    for ms in (0, 500, 900):
        scenes.update(replace(base, frame=replace(base.frame, source_ts_ms=ms)), config)
    reset = replace(base, frame=replace(base.frame, source_ts_ms=1000, discontinuity=True))
    assert not loiter_events(scenes.update(reset, config).events)
    assert not loiter_events(
        scenes.update(replace(base, frame=replace(base.frame, source_ts_ms=1500)), config).events
    )
    assert (
        len(
            loiter_events(
                scenes.update(
                    replace(base, frame=replace(base.frame, source_ts_ms=2100)), config
                ).events
            )
        )
        == 1
    )


def test_brief_outside_resets_unfired_continuous_timer_without_new_visit() -> None:
    engine = ZoneEngine(FixedClock())
    config = CameraConfig(loitering_threshold_seconds=2)
    for ms in (0, 1000, 1900):
        assert not loiter_events(tick(engine, ms, config=config)[1])
    tick(engine, 1950, inside=False, config=config)
    for ms in (2000, 3000, 4000):
        assert not loiter_events(tick(engine, ms, config=config)[1])
    assert len(loiter_events(tick(engine, 4001, config=config)[1])) == 1


@pytest.mark.parametrize("threshold", [0.3, 1.0, 10.0])
def test_loitering_no_accumulated_float_error_at_exact_threshold(threshold: float) -> None:
    engine = ZoneEngine(FixedClock())
    config = CameraConfig(loitering_threshold_seconds=threshold, zone_enter_dwell_seconds=0)
    for ms in range(0, int(threshold * 1000) + 1, 100):
        assert not loiter_events(tick(engine, ms, config=config)[1])
    assert len(loiter_events(tick(engine, threshold * 1000 + 1, config=config)[1])) == 1


@pytest.mark.parametrize(
    "invalid", ["missing_zone", "line_reference", "entry_metadata", "threshold_not_exceeded"]
)
def test_loitering_payload_rejects_wrong_refs_or_duration(invalid: str) -> None:
    from pydantic import ValidationError

    engine = ZoneEngine(FixedClock())
    config = CameraConfig(loitering_threshold_seconds=0.1)
    tick(engine, 0, config=config)
    event = loiter_events(tick(engine, 300, config=config)[1])[0]
    raw = event.model_dump()
    if invalid == "missing_zone":
        raw["zone_id"] = None
    elif invalid == "line_reference":
        raw["line_id"] = uuid4()
    elif invalid == "entry_metadata":
        raw["metadata"] = {
            "bbox": (0.1, 0.1, 0.5, 0.5),
            "anchor": (0.3, 0.5),
            "dwell_seconds": 1,
            "stability": 1,
        }
    else:
        raw["metadata"]["duration_seconds"] = raw["metadata"]["threshold_seconds"]
    with pytest.raises(ValidationError):
        DomainEvent.model_validate(raw)
