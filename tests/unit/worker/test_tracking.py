"""Real ByteTrack with synthetic observations: no neural network or weights."""

from collections.abc import Sequence
from dataclasses import FrozenInstanceError, replace
from uuid import uuid4

import pytest
from worker_fakes import make_frame

from ai_detector_core.people.track import PersonState, PersonTrack
from vision_worker.cameras.frame import Frame
from vision_worker.config import WorkerSettings
from vision_worker.inference.detector import PersonDetection
from vision_worker.pipeline.frame_buffer import LatestFrameBuffer
from vision_worker.pipeline.preview import encode_packet
from vision_worker.pipeline.results import DetectionResult
from vision_worker.tracking.bytetrack import ByteTrackPersonTracker
from vision_worker.tracking.registry import TrackerRegistry


def person(x: float = 10, confidence: float = 0.9) -> PersonDetection:
    return PersonDetection((x, 10, x + 30, 90), confidence)


def test_stable_ids_motion_and_observation_fields() -> None:
    camera, run = uuid4(), uuid4()
    tracker = ByteTrackPersonTracker(camera, run)
    assert tracker.update(make_frame(1, 200, 100), [person()]) == ()
    first = tracker.update(make_frame(2, 200, 100), [person(11)])[0]
    for i in range(3, 12):
        current = tracker.update(make_frame(i, 200, 100), [person(9 + i)])[0]
        assert current.track_id == first.track_id
        assert current.state == PersonState.NORMAL
        assert current.hits == current.age == i - 1
        assert current.missed_frames == 0
        assert current.last_source_ts_ms == i * 40
        assert current.first_source_ts_ms == 80
        assert current.camera_id == camera and current.run_id == run
        assert current.anchor == (24 + i, 90)
        assert current.center == (24 + i, 50)
    with pytest.raises(FrozenInstanceError):
        first.age = 999  # type: ignore[misc]


def test_empty_frames_age_lost_tracks_and_recover_same_id() -> None:
    tracker = ByteTrackPersonTracker(uuid4(), uuid4())
    tracker.update(make_frame(1), [person()])
    first = tracker.update(make_frame(2), [person()])[0]
    for i in range(3, 8):
        lost = tracker.update(make_frame(i), [])[0]
        assert lost.state == PersonState.LOST
        assert lost.age == i - 1 and lost.hits == 1 and lost.missed_frames == i - 2
        assert lost.last_source_ts_ms == first.last_source_ts_ms
    found = tracker.update(make_frame(8), [person()])[0]
    assert found.track_id == first.track_id
    assert found.state == PersonState.NORMAL and found.missed_frames == 0
    assert found.hits == 2 and found.age == 7


def test_exact_25_missed_frames_expire_without_resurrection() -> None:
    tracker = ByteTrackPersonTracker(uuid4(), uuid4())
    tracker.update(make_frame(1), [person()])
    original = tracker.update(make_frame(2), [person()])[0].track_id
    for i in range(1, 25):
        assert tracker.update(make_frame(i + 2), [])[0].missed_frames == i
    assert tracker.update(make_frame(27), []) == ()
    assert not tracker._tracks and not tracker._tracker.tracks
    tracker.update(make_frame(28), [person()])
    new = tracker.update(make_frame(29), [person()])[0]
    assert new.track_id > original


def test_recovery_at_last_retained_frame() -> None:
    tracker = ByteTrackPersonTracker(uuid4(), uuid4(), max_age=3)
    tracker.update(make_frame(1), [person()])
    original = tracker.update(make_frame(2), [person()])[0].track_id
    tracker.update(make_frame(3), [])
    tracker.update(make_frame(4), [])
    assert tracker.update(make_frame(5), [person()])[0].track_id == original


def test_low_confidence_recovers_but_cannot_create_a_track() -> None:
    tracker = ByteTrackPersonTracker(uuid4(), uuid4())
    for i in range(1, 4):
        assert tracker.update(make_frame(i), [person(confidence=0.24)]) == ()
    tracker.update(make_frame(4), [person(confidence=0.25)])
    original = tracker.update(make_frame(5), [person(confidence=0.25)])[0]
    recovered = tracker.update(make_frame(6), [person(confidence=0.15)])[0]
    assert recovered.track_id == original.track_id
    assert recovered.confidence == pytest.approx(0.15)


def test_iou_gate_and_detection_order_do_not_swap_ids() -> None:
    tracker = ByteTrackPersonTracker(uuid4(), uuid4())
    tracker.update(make_frame(1), [person(10), person(100)])
    first = tracker.update(make_frame(2), [person(10), person(100)])
    reordered = tracker.update(make_frame(3), [person(100), person(10)])
    assert [(t.track_id, t.bbox) for t in first] == [(t.track_id, t.bbox) for t in reordered]
    far = tracker.update(make_frame(4), [person(300)])
    assert all(t.state == PersonState.LOST for t in far)
    new = tracker.update(make_frame(5), [person(300)])
    assert new[-1].track_id not in {t.track_id for t in first}


def test_reset_clears_scene_without_reusing_public_ids() -> None:
    tracker = ByteTrackPersonTracker(uuid4(), uuid4())
    tracker.update(make_frame(1), [person()])
    previous = tracker.update(make_frame(2), [person()])[0].track_id
    tracker.reset()
    tracker.update(make_frame(3), [person()])
    assert tracker.update(make_frame(4), [person()])[0].track_id > previous


def test_cameras_runs_and_registry_cleanup_are_independent() -> None:
    registry = TrackerRegistry()
    camera, run = uuid4(), uuid4()
    keys = {(camera, run), (uuid4(), uuid4()), (camera, uuid4())}
    for cid, rid in keys:
        for i in (1, 2):
            tracks = registry.update(DetectionResult(cid, rid, make_frame(i), (person(),), 0))
        assert tracks[0].track_id == 1 and tracks[0].run_id == rid
    registry.retain({(camera, run)})
    assert set(registry._entries) == {(camera, run)}
    registry.retain(set())
    assert not registry._entries


@pytest.mark.parametrize("change", ["epoch", "size", "discontinuity"])
def test_scene_change_resets_tracker_even_if_flag_frame_was_dropped(change: str) -> None:
    registry = TrackerRegistry()
    cid, rid = uuid4(), uuid4()
    for i in (1, 2):
        original = registry.update(DetectionResult(cid, rid, make_frame(i), (person(),), 0))
    if change == "epoch":
        buffer = LatestFrameBuffer()
        buffer.put(replace(make_frame(3), discontinuity=True, source_epoch=1))
        buffer.put(replace(make_frame(4), source_epoch=1))
        frame = buffer.take()
        assert frame is not None and not frame.discontinuity
    elif change == "size":
        frame = make_frame(4, 300, 200)
    else:
        frame = replace(make_frame(4), discontinuity=True)
    assert registry.update(DetectionResult(cid, rid, frame, (person(),), 0)) == ()
    frame = replace(frame, frame_id=5, discontinuity=False)
    current = registry.update(DetectionResult(cid, rid, frame, (person(),), 0))[0]
    assert current.track_id > original[0].track_id


def test_preview_tracks_share_exact_frame_and_lost_state() -> None:
    import json
    import struct

    cid, rid = uuid4(), uuid4()
    registry = TrackerRegistry()
    for i in (1, 2):
        result = DetectionResult(cid, rid, make_frame(i, 100, 100), (person(),), 0)
        tracks = registry.update(result)
    packet = encode_packet(replace(result, tracks=tracks), 640)
    size = struct.unpack("!I", packet[:4])[0]
    header = json.loads(packet[4 : 4 + size])
    assert header["tracks"][0]["track_id"] == tracks[0].track_id
    assert header["tracks"][0]["bbox"] == pytest.approx([0.1, 0.1, 0.4, 0.9])
    assert header["tracks"][0]["state"] == "NORMAL"
    assert header["frame_id"] == 2 and header["run_id"] == str(rid)


@pytest.mark.parametrize(
    "patch",
    [
        {"person_track_max_age": 0},
        {"track_match_iou": 0},
        {"track_match_iou": 1.1},
        {"track_activation_confidence": 0},
    ],
)
def test_tracking_configuration_rejects_invalid_settings(patch: dict[str, float]) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WorkerSettings.model_validate(patch)


@pytest.mark.parametrize(
    "threshold, expected", [(0.4, PersonState.NORMAL), (0.5, PersonState.LOST)]
)
def test_configured_iou_is_a_true_overlap_threshold(
    threshold: float, expected: PersonState
) -> None:
    tracker = ByteTrackPersonTracker(uuid4(), uuid4(), match_iou=threshold)
    tracker.update(make_frame(1), [person(10)])
    tracker.update(make_frame(2), [person(10)])
    # IoU = 18 / 42, no confidence-score fusion changes the configured gate.
    assert tracker.update(make_frame(3), [person(22)])[0].state == expected


def test_registry_storage_does_not_accumulate_expired_history() -> None:
    tracker = ByteTrackPersonTracker(uuid4(), uuid4(), max_age=1)
    previous = 0
    for cycle in range(50):
        tracker.update(make_frame(cycle * 3 + 1), [person()])
        track = tracker.update(make_frame(cycle * 3 + 2), [person()])[0]
        assert track.track_id > previous
        previous = track.track_id
        assert tracker.update(make_frame(cycle * 3 + 3), []) == ()
        assert not tracker._tracks and not tracker._tracker.tracks


def test_failed_update_resets_partial_scene_and_propagates() -> None:
    class FailingTracker:
        resets = 0

        def update(
            self, frame: Frame, detections: Sequence[PersonDetection]
        ) -> tuple[PersonTrack, ...]:
            raise RuntimeError("partial tracker update")

        def reset(self) -> None:
            self.resets += 1

    broken = FailingTracker()
    registry = TrackerRegistry(lambda _cid, _rid: broken)
    with pytest.raises(RuntimeError, match="partial tracker update"):
        registry.update(DetectionResult(uuid4(), uuid4(), make_frame(1), (), 0))
    assert broken.resets == 1
