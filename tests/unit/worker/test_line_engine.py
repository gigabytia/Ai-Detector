"""Both signed directions, finite segment, hysteresis, LOST, lifecycle and confidence."""

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from worker_fakes import make_frame

from ai_detector_core.cameras.config import CameraConfig
from ai_detector_core.events.domain import DomainEvent, LineCrossMetadata, ZoneEntryMetadata
from ai_detector_core.lines.model import LineShape, LineSpec
from ai_detector_core.people.track import PersonState, PersonTrack
from fakes import FixedClock
from vision_worker.pipeline.results import DetectionResult
from vision_worker.rules.line_engine import LineEngine
from vision_worker.rules.registry import SceneRegistry

CID, RID, LID = uuid4(), uuid4(), uuid4()
LINE = LineSpec(
    id=LID, camera_id=CID, name="Вход", p1={"x": 0.2, "y": 0.5}, p2={"x": 0.8, "y": 0.5}
)
CONFIG = CameraConfig(event_cooldown_seconds=0)


def track(
    x: float = 0.5,
    y: float = 0.3,
    *,
    lost: bool = False,
    hits: int = 10,
    tid: int = 1,
    confidence: float = 0.8,
) -> PersonTrack:
    at = make_frame(0).captured_at
    return PersonTrack(
        tid,
        CID,
        RID,
        (x * 100 - 2, y * 100 - 5, x * 100 + 2, y * 100),
        confidence,
        at,
        at,
        0,
        100,
        10,
        hits,
        1 if lost else 0,
        PersonState.LOST if lost else PersonState.NORMAL,
    )


def tick(
    engine: LineEngine,
    y: float = 0.3,
    x: float = 0.5,
    *,
    lines: tuple[LineSpec, ...] = (LINE,),
    config: CameraConfig = CONFIG,
    lost: bool = False,
    hits: int = 10,
    tid: int = 1,
    confidence: float = 0.8,
) -> tuple[DomainEvent, ...]:
    return engine.update(
        make_frame(1, 100, 100),
        (track(x, y, lost=lost, hits=hits, tid=tid, confidence=confidence),),
        lines,
        config,
    )


@pytest.mark.parametrize(
    "p1,p2",
    [
        ({"x": 0, "y": 0}, {"x": 0, "y": 0}),
        ({"x": -1, "y": 0}, {"x": 1, "y": 1}),
        ({"x": float("nan"), "y": 0}, {"x": 1, "y": 1}),
        ({"x": 0, "y": 0}, {"x": 1e-8, "y": 0}),
    ],
)
def test_line_shape_rejects_invalid_geometry(p1: dict[str, float], p2: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        LineShape(name="x", p1=p1, p2=p2)


def test_both_directions_initial_baseline_and_repeated_same_side() -> None:
    engine = LineEngine(FixedClock())
    assert not tick(engine)
    events = tick(engine, 0.7)
    assert len(events) == 1 and events[0].type == "PERSON_CROSSED_LINE"
    event = events[0]
    assert event.zone_id is None and event.line_id == LID and event.severity == "warning"
    assert (
        isinstance(event.metadata, LineCrossMetadata)
        and event.metadata.direction == "LEFT_TO_RIGHT"
    )
    assert event.metadata.p1 == (0.2, 0.5) and event.metadata.p2 == (0.8, 0.5)
    assert event.metadata.anchor == (0.5, 0.7) and event.metadata.line_name == "Вход"
    assert not tick(engine, 0.8)
    reverse = tick(engine, 0.2)[0]
    assert (
        isinstance(reverse.metadata, LineCrossMetadata)
        and reverse.metadata.direction == "RIGHT_TO_LEFT"
    )
    assert reverse.id != event.id


def test_hysteresis_band_threshold_touch_and_drift_are_not_crossings() -> None:
    engine = LineEngine(FixedClock())
    for y in [0.5, 0.501, 0.499, 0.51, 0.49, 0.3, 0.495, 0.505, 0.5]:
        assert not tick(engine, y)
    assert len(tick(engine, 0.52)) == 1
    for y in [0.5, 0.491, 0.509, 0.7]:
        assert not tick(engine, y)


@pytest.mark.parametrize("x", [0.1, 0.9])
def test_extension_is_not_segment_and_does_not_defer_crossing(x: float) -> None:
    engine = LineEngine(FixedClock())
    tick(engine, 0.3, x)
    assert not tick(engine, 0.7, x)
    assert not tick(engine, 0.7, 0.5)  # moving along side into segment is not crossing


@pytest.mark.parametrize("x", [0.2, 0.8])
def test_segment_endpoints_are_inclusive(x: float) -> None:
    engine = LineEngine(FixedClock())
    tick(engine, 0.3, x)
    assert len(tick(engine, 0.7, x)) == 1


def test_reversing_endpoints_reverses_direction() -> None:
    line = LINE.model_copy(update={"p1": LINE.p2, "p2": LINE.p1})
    engine = LineEngine(FixedClock())
    tick(engine, 0.3, lines=(line,))
    event = tick(engine, 0.7, lines=(line,))[0]
    assert (
        isinstance(event.metadata, LineCrossMetadata)
        and event.metadata.direction == "RIGHT_TO_LEFT"
    )


def test_lost_freezes_side_recovery_crosses_and_window_reduces_confidence() -> None:
    engine = LineEngine(FixedClock())
    tick(engine, 0.3, confidence=0.6)
    assert not tick(engine, 0.7, lost=True)
    event = tick(engine, 0.7, confidence=0.9)[0]
    assert event.detector_confidence == pytest.approx(0.75)
    assert event.event_confidence == pytest.approx(0.5)
    assert event.metadata.stability == pytest.approx(2 / 3)


def test_unconfirmed_and_deleted_tracks_do_not_cross() -> None:
    engine = LineEngine(FixedClock())
    tick(engine, 0.3, hits=1)
    assert not tick(engine, 0.7, hits=2)
    assert not tick(engine, 0.8, hits=3)
    engine.update(make_frame(2, 100, 100), (), (LINE,), CONFIG)
    assert not tick(engine, 0.2)


def test_cooldown_is_wall_clock_and_side_advances_when_suppressed() -> None:
    clock = FixedClock()
    engine = LineEngine(clock)
    config = CameraConfig(event_cooldown_seconds=3)
    tick(engine, 0.3, config=config)
    assert len(tick(engine, 0.7, config=config)) == 1
    assert not tick(engine, 0.3, config=config)
    clock.advance(4)
    assert not tick(engine, 0.2, config=config)
    assert len(tick(engine, 0.7, config=config)) == 1


def test_geometry_edit_disable_delete_and_rename_behavior() -> None:
    engine = LineEngine(FixedClock())
    tick(engine, 0.3)
    renamed = LINE.model_copy(update={"name": "новое"})
    event = tick(engine, 0.7, lines=(renamed,))[0]
    assert isinstance(event.metadata, LineCrossMetadata) and event.metadata.line_name == "новое"
    changed = LINE.model_copy(update={"p1": LINE.p2, "p2": LINE.p1})
    assert not tick(engine, 0.2, lines=(changed,))  # no stale baseline after edit
    assert not tick(engine, 0.7, lines=(changed.model_copy(update={"enabled": False}),))
    assert not tick(engine, 0.7, lines=(changed,))
    assert not tick(engine, 0.2, lines=())
    assert not tick(engine, 0.2, lines=(LINE,))


def test_multiple_lines_and_camera_run_state_isolation() -> None:
    engine = LineEngine(FixedClock())
    second = LINE.model_copy(update={"id": uuid4()})
    tick(engine, 0.3, lines=(LINE, second))
    assert len(tick(engine, 0.7, lines=(LINE, second))) == 2
    registry = SceneRegistry(FixedClock())

    def result(y: float, run: UUID = RID) -> DetectionResult:
        t = replace(track(y=y), run_id=run)
        return DetectionResult(CID, run, make_frame(0, 100, 100), (), 0, tracks=(t,), lines=(LINE,))

    registry.update(result(0.3), CONFIG)
    assert not registry.update(result(0.7, uuid4()), CONFIG).events
    assert registry.update(result(0.7), CONFIG).events
    registry.retain(set())
    assert not registry.update(result(0.3), CONFIG).events


@pytest.mark.parametrize("reset", ["epoch", "discontinuity", "size"])
def test_scene_reset_prevents_synthetic_crossings(reset: str) -> None:
    registry = SceneRegistry(FixedClock())
    first = DetectionResult(
        CID, RID, make_frame(0, 100, 100), (), 0, tracks=(track(y=0.3),), lines=(LINE,)
    )
    registry.update(first, CONFIG)
    frame = (
        replace(first.frame, source_epoch=1)
        if reset == "epoch"
        else replace(first.frame, discontinuity=True)
        if reset == "discontinuity"
        else make_frame(1, 120, 100)
    )
    assert not registry.update(replace(first, frame=frame, tracks=(track(y=0.7),)), CONFIG).events


def test_domain_event_enforces_type_reference_and_metadata_pair() -> None:
    engine = LineEngine(FixedClock())
    tick(engine)
    event = tick(engine, 0.7)[0]
    assert DomainEvent.model_validate_json(event.model_dump_json()) == event
    changes: list[dict[str, object]] = [
        {"type": "PERSON_ENTERED_DANGER_ZONE"},
        {"line_id": None},
        {"zone_id": uuid4()},
        {
            "metadata": ZoneEntryMetadata(
                bbox=(0, 0, 1, 1), anchor=(0.5, 0.5), dwell_seconds=0, stability=1
            )
        },
    ]
    for change in changes:
        with pytest.raises(ValidationError):
            DomainEvent.model_validate({**event.model_dump(), **change})


def test_cooldown_is_shared_across_lines_but_not_tracks() -> None:
    engine = LineEngine(FixedClock())
    second = LINE.model_copy(update={"id": uuid4()})
    lines = (LINE, second)
    config = CameraConfig(event_cooldown_seconds=3)
    tick(engine, 0.3, lines=lines, config=config)
    assert len(tick(engine, 0.7, lines=lines, config=config)) == 1
    tick(engine, 0.3, tid=2, lines=lines, config=config)
    assert len(tick(engine, 0.7, tid=2, lines=lines, config=config)) == 1


def test_zone_and_line_can_emit_together_without_changing_person_state() -> None:
    from ai_detector_core.zones.model import ZoneSpec

    zone = ZoneSpec(
        id=uuid4(),
        camera_id=CID,
        name="Зона",
        points=[
            {"x": 0.2, "y": 0.4},
            {"x": 0.8, "y": 0.4},
            {"x": 0.8, "y": 0.9},
            {"x": 0.2, "y": 0.9},
        ],
    )
    registry = SceneRegistry(FixedClock())
    config = CameraConfig(zone_enter_dwell_seconds=0, event_cooldown_seconds=3)

    def result(y: float) -> DetectionResult:
        return DetectionResult(
            CID,
            RID,
            make_frame(0, 100, 100),
            (),
            0,
            tracks=(track(y=y),),
            zones=(zone,),
            lines=(LINE,),
        )

    registry.update(result(0.3), config)
    current = registry.update(result(0.7), config)
    assert {e.type for e in current.events} == {"PERSON_ENTERED_DANGER_ZONE", "PERSON_CROSSED_LINE"}
    assert current.tracks[0].state == PersonState.IN_DANGER_ZONE
