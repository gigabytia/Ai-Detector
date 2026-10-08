import pytest

from vision_worker.cameras.mock_source import MockFrameSource, make_background, render_scene
from vision_worker.cameras.scenario import (
    Keyframe,
    Scenario,
    ScriptedPerson,
    UnknownScenarioError,
    load_scenario,
)
from vision_worker.cameras.source import SourceFatalError


@pytest.mark.parametrize("name", ["walk_through", "two_people"])
def test_bundled_scenarios_load(name: str) -> None:
    scenario = load_scenario(name)
    assert scenario.name == name
    assert scenario.people


def test_unknown_scenario() -> None:
    with pytest.raises(UnknownScenarioError):
        load_scenario("nope")
    with pytest.raises(SourceFatalError):
        MockFrameSource("nope").start()


def test_person_moves_linearly_and_disappears_outside_keyframes() -> None:
    person = ScriptedPerson(
        id=1,
        keyframes=[
            Keyframe(t=1, bbox=(0.0, 0.0, 0.2, 0.4)),
            Keyframe(t=3, bbox=(0.4, 0.2, 0.6, 0.6)),
        ],
    )
    assert person.bbox_at(0.5) is None
    assert person.bbox_at(2) == pytest.approx((0.2, 0.1, 0.4, 0.5))
    assert person.bbox_at(3.5) is None


def test_invalid_keyframes_are_rejected() -> None:
    with pytest.raises(ValueError):
        Keyframe(t=0, bbox=(0.5, 0.5, 0.4, 0.6))
    with pytest.raises(ValueError):
        ScriptedPerson(
            id=1,
            keyframes=[Keyframe(t=2, bbox=(0, 0, 1, 1)), Keyframe(t=1, bbox=(0, 0, 1, 1))],
        )


def test_render_draws_people_on_background() -> None:
    scenario = Scenario(
        name="t",
        width=160,
        height=90,
        fps=10,
        duration_s=2,
        people=[
            ScriptedPerson(
                id=1,
                keyframes=[
                    Keyframe(t=0, bbox=(0.4, 0.2, 0.6, 0.9)),
                    Keyframe(t=2, bbox=(0.4, 0.2, 0.6, 0.9)),
                ],
            )
        ],
    )
    background = make_background(160, 90)
    image = render_scene(background, scenario, 1.0)
    assert image.shape == (90, 160, 3)
    assert (image != background).any()
    assert (image[:, :40] == background[:, :40]).all()  # nothing drawn outside the person


def test_mock_source_frames_follow_scenario_fps() -> None:
    source = MockFrameSource("walk_through")
    source.start()
    try:
        frames = [source.read() for _ in range(3)]
    finally:
        source.stop()
        source.close()
    real = [f for f in frames if f is not None]
    assert [f.frame_id for f in real] == [1, 2, 3]
    assert [f.source_ts_ms for f in real] == pytest.approx([0, 1000 / 15, 2000 / 15])
    assert real[0].size == (1280, 720)
