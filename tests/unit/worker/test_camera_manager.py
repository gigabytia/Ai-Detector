import uuid

import pytest

from ai_detector_core.cameras.source import SourceType
from ai_detector_core.cameras.spec import CameraSpec
from ai_detector_core.cameras.status import CameraRuntimeStatus, CameraStatus
from vision_worker.cameras.manager import CameraManager


class FakeSession:
    def __init__(self, spec: CameraSpec) -> None:
        self.spec = spec
        self.state = CameraStatus.CREATED
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True
        self.state = CameraStatus.RUNNING

    def stop(self) -> None:
        self.stopped = True
        self.state = CameraStatus.STOPPED

    def status(self) -> CameraRuntimeStatus:
        raise NotImplementedError


def spec(
    name: str = "cam",
    url: str = "mock://walk_through",
    enabled: bool = True,
    camera_id: uuid.UUID | None = None,
) -> CameraSpec:
    return CameraSpec(
        id=camera_id or uuid.uuid4(),
        name=name,
        source_type=SourceType.MOCK,
        source_url=url,
        enabled=enabled,
    )


class Recorder:
    def __init__(self) -> None:
        self.created: list[FakeSession] = []

    def __call__(self, s: CameraSpec) -> FakeSession:
        session = FakeSession(s)
        self.created.append(session)
        return session


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


async def test_reconcile_starts_enabled_and_stops_removed(recorder: Recorder) -> None:
    manager = CameraManager(recorder)
    a, b, off = spec("a"), spec("b"), spec("off", enabled=False)
    await manager.reconcile([a, b, off])
    assert {s.spec.id for s in manager.sessions} == {a.id, b.id}
    first_a = recorder.created[0]

    await manager.reconcile([a])
    assert [s.spec.id for s in manager.sessions] == [a.id]
    assert recorder.created[1].stopped
    assert not first_a.stopped  # unchanged camera keeps running


async def test_rename_keeps_session_but_source_change_restarts(recorder: Recorder) -> None:
    manager = CameraManager(recorder)
    cam = spec("old")
    await manager.apply(cam.id, cam)
    renamed = spec("new", camera_id=cam.id)
    await manager.apply(cam.id, renamed)
    assert len(recorder.created) == 1
    assert manager.sessions[0].spec.name == "new"

    moved = spec("new", url="mock://two_people", camera_id=cam.id)
    await manager.apply(cam.id, moved)
    assert len(recorder.created) == 2
    assert recorder.created[0].stopped


async def test_errored_session_is_recreated_on_apply(recorder: Recorder) -> None:
    manager = CameraManager(recorder)
    cam = spec()
    await manager.apply(cam.id, cam)
    recorder.created[0].state = CameraStatus.ERROR
    await manager.apply(cam.id, cam)
    assert len(recorder.created) == 2


async def test_disable_delete_restart_and_stop_all(recorder: Recorder) -> None:
    manager = CameraManager(recorder)
    a, b = spec("a"), spec("b")
    await manager.reconcile([a, b])
    await manager.apply(a.id, spec("a", enabled=False, camera_id=a.id))
    await manager.apply(b.id, None)
    assert manager.sessions == []

    await manager.restart(a.id, a)
    await manager.restart(a.id, a)
    assert len(recorder.created) == 4
    assert recorder.created[2].stopped

    await manager.restart(uuid.uuid4(), None)  # unknown and deleted: nothing happens
    await manager.stop_all()
    assert manager.sessions == []
    assert all(s.stopped for s in recorder.created)
