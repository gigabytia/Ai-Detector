"""Deterministic membership, timing, confidence, resets and cooldown."""

from dataclasses import replace
from uuid import uuid4

import pytest
from worker_fakes import make_frame

from ai_detector_core.cameras.config import CameraConfig
from ai_detector_core.events.domain import DomainEvent
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
