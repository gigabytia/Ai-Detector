import uuid
from typing import cast

from redis.asyncio import Redis

from ai_detector_core.cameras.source import SourceType
from ai_detector_core.cameras.spec import CameraSpec
from ai_detector_core.telemetry.commands import WorkerCommand, WorkerCommandType
from vision_worker.cameras.manager import CameraManager
from vision_worker.cameras.reconnect import BackoffPolicy
from vision_worker.cameras.spec_client import CameraSpecClient, SpecUnavailableError
from vision_worker.messaging.commands import CommandListener

CAM = CameraSpec(
    id=uuid.uuid4(), name="c", source_type=SourceType.MOCK, source_url="mock://x", enabled=True
)


class FakeSpecs:
    def __init__(self) -> None:
        self.specs: dict[uuid.UUID, CameraSpec] = {CAM.id: CAM}
        self.fail = False

    async def list_enabled(self) -> list[CameraSpec]:
        if self.fail:
            raise SpecUnavailableError("down")
        return list(self.specs.values())

    async def get(self, camera_id: uuid.UUID) -> CameraSpec | None:
        if self.fail:
            raise SpecUnavailableError("down")
        return self.specs.get(camera_id)


class FakeManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def reconcile(self, specs: list[CameraSpec]) -> None:
        self.calls.append(("reconcile", [s.id for s in specs]))

    async def apply(self, camera_id: uuid.UUID, spec: CameraSpec | None) -> None:
        self.calls.append(("apply", (camera_id, spec)))

    async def restart(self, camera_id: uuid.UUID, spec: CameraSpec | None) -> None:
        self.calls.append(("restart", (camera_id, spec)))


def make_listener() -> tuple[CommandListener, FakeSpecs, FakeManager]:
    specs, manager = FakeSpecs(), FakeManager()
    listener = CommandListener(
        redis=cast(Redis, object()),
        specs=cast(CameraSpecClient, specs),
        manager=cast(CameraManager, manager),
        retry=BackoffPolicy(initial_seconds=1, max_seconds=1),
    )
    return listener, specs, manager


def command(kind: WorkerCommandType, camera_id: uuid.UUID) -> str:
    return WorkerCommand(type=kind, camera_id=camera_id).model_dump_json()


async def test_changed_and_restart_commands_reach_manager() -> None:
    listener, _, manager = make_listener()
    await listener._handle(command(WorkerCommandType.CAMERA_CHANGED, CAM.id))
    await listener._handle(command(WorkerCommandType.CAMERA_RESTART, CAM.id))
    gone = uuid.uuid4()
    await listener._handle(command(WorkerCommandType.CAMERA_CHANGED, gone))
    assert manager.calls == [
        ("apply", (CAM.id, CAM)),
        ("restart", (CAM.id, CAM)),
        ("apply", (gone, None)),  # deleted camera: manager stops it
    ]


async def test_invalid_command_is_ignored() -> None:
    listener, _, manager = make_listener()
    await listener._handle(b'{"type": "camera.explode"}')
    await listener._handle("not json")
    assert manager.calls == []


async def test_api_outage_schedules_full_reconcile() -> None:
    listener, specs, manager = make_listener()
    await listener._full_reconcile()
    assert manager.calls == [("reconcile", [CAM.id])]
    assert listener._needs_full_reconcile is False

    specs.fail = True
    await listener._handle(command(WorkerCommandType.CAMERA_CHANGED, CAM.id))
    assert listener._needs_full_reconcile is True
    await listener._full_reconcile()  # still down: keeps sessions, retries later
    assert listener._needs_full_reconcile is True
    assert len(manager.calls) == 1

    specs.fail = False
    await listener._full_reconcile()
    assert listener._needs_full_reconcile is False
