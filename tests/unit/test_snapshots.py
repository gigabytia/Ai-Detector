"""Snapshot capture is optional, bounded, full-resolution, and never draws pixels."""

import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import cv2
import numpy as np
import pytest
from pydantic import ValidationError
from redis.asyncio import Redis
from test_event_transport import event

from ai_detector_core.events.transport import EventMessage, SnapshotMetadata
from ai_detector_core.storage.snapshots import LocalSnapshotStorage, snapshot_key
from vision_worker.cameras.frame import Frame
from vision_worker.messaging.events import EventPublisher
from vision_worker.storage.snapshot_writer import SnapshotWriter


def test_storage_roundtrip_atomic_replace_and_delete(tmp_path: Path) -> None:
    storage = LocalSnapshotStorage(tmp_path)
    key = snapshot_key(uuid4(), datetime.now(UTC), uuid4())
    storage.put(key, b"first")
    storage.put(key, b"second")
    with storage.open(key) as file:
        assert file.read() == b"second"
    assert not list(tmp_path.rglob("*.part"))
    storage.delete(key)
    storage.delete(key)
    with pytest.raises(FileNotFoundError):
        storage.open(key)


@pytest.mark.parametrize(
    "key",
    [
        "../../etc/passwd",
        "/absolute/image.jpg",
        "snapshots/a/2026/01/01/b.jpg",
        "snapshots/00000000-0000-0000-0000-000000000000/2026/02/31/00000000-0000-0000-0000-000000000000.jpg",
    ],
)
def test_rejects_noncanonical_paths(tmp_path: Path, key: str) -> None:
    storage = LocalSnapshotStorage(tmp_path)
    actions: list[Callable[[], object]] = [
        lambda: storage.put(key, b"x"),
        lambda: storage.open(key),
        lambda: storage.delete(key),
    ]
    for action in actions:
        with pytest.raises(ValueError):
            action()


def test_rejects_symlink_components_and_files(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    camera = uuid4()
    (root / str(camera)).symlink_to(outside, target_is_directory=True)
    storage = LocalSnapshotStorage(root)
    key = snapshot_key(camera, datetime.now(UTC), uuid4())
    with pytest.raises(ValueError):
        storage.put(key, b"x")
    assert not list(outside.iterdir())
    key = snapshot_key(uuid4(), datetime.now(UTC), uuid4())
    storage.put(key, b"jpeg")
    path = root / key.removeprefix("snapshots/")
    path.unlink()
    path.symlink_to(outside / "secret")
    with pytest.raises(ValueError):
        storage.open(key)


def test_failed_atomic_replace_removes_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalSnapshotStorage(tmp_path)
    key = snapshot_key(uuid4(), datetime.now(UTC), uuid4())

    def fail(*args: object) -> None:
        raise OSError("disk failed")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError):
        storage.put(key, b"jpeg")
    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("*.jpg"))


def test_transport_binds_attachment_to_event_and_camera() -> None:
    original = event()
    metadata = SnapshotMetadata(
        id=uuid4(),
        event_id=original.id,
        storage_key=snapshot_key(original.camera_id, original.occurred_at, uuid4()),
        width=10,
        height=20,
        size_bytes=100,
        created_at=datetime.now(UTC),
    )
    with pytest.raises(ValidationError):
        EventMessage(**original.model_dump(), snapshot=metadata)
    metadata = metadata.model_copy(
        update={"storage_key": snapshot_key(original.camera_id, original.occurred_at, metadata.id)}
    )
    assert EventMessage(**original.model_dump(), snapshot=metadata).snapshot == metadata
    with pytest.raises(ValidationError):
        EventMessage(
            **original.model_dump(), snapshot=metadata.model_copy(update={"event_id": uuid4()})
        )


async def test_writer_full_resolution_unmodified_frame_and_disabled(tmp_path: Path) -> None:
    publisher = EventPublisher(cast(Redis, object()))
    storage = LocalSnapshotStorage(tmp_path)
    writer = SnapshotWriter(storage, publisher)
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[:] = (30, 70, 110)
    frame = Frame(image, 1, 100, datetime.now(UTC))
    original = event()
    before = image.copy()
    writer.offer(original, frame, True)
    disabled = event()
    writer.offer(disabled, frame, False)
    await writer.close()
    messages = [publisher.queue.get_nowait(), publisher.queue.get_nowait()]
    assert messages[0] is disabled
    message = messages[1]
    assert isinstance(message, EventMessage) and message.snapshot
    assert (message.snapshot.width, message.snapshot.height) == (1280, 720)
    with storage.open(message.snapshot.storage_key) as file:
        data = file.read()
    decoded = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert (
        decoded.shape == image.shape
        and np.max(np.abs(decoded.astype(int) - image.astype(int))) <= 2
    )
    assert np.array_equal(image, before)
    assert message.id == original.id and message.snapshot.size_bytes == len(data)
    assert len(await asyncio.to_thread(lambda: list(tmp_path.rglob("*.jpg")))) == 1


async def test_writer_failure_and_capacity_fall_back_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher = EventPublisher(cast(Redis, object()))
    storage = LocalSnapshotStorage(tmp_path)
    writer = SnapshotWriter(storage, publisher, capacity=1)
    frame = Frame(np.zeros((10, 20, 3), dtype=np.uint8), 1, 1, datetime.now(UTC))

    def fail(*args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(storage, "put", fail)
    first, second = event(), event()
    writer.offer(first, frame, True)
    writer.offer(second, frame, True)
    assert publisher.queue.get_nowait() is second  # no encode/disk await in offer
    await asyncio.wait_for(writer.close(), 2)
    assert publisher.queue.get_nowait() is first
    assert not await asyncio.to_thread(lambda: list(tmp_path.rglob("*.jpg")))


def test_orphan_and_temporary_age_scan(tmp_path: Path) -> None:
    storage = LocalSnapshotStorage(tmp_path)
    old = datetime.now(UTC) - timedelta(days=40)
    key = snapshot_key(uuid4(), old, uuid4())
    storage.put(key, b"jpeg")
    path = tmp_path / key.removeprefix("snapshots/")
    os.utime(path, (old.timestamp(), old.timestamp()))
    temp = path.parent / ".snapshot-crash.part"
    temp.write_bytes(b"tmp")
    os.utime(temp, (old.timestamp(), old.timestamp()))
    recent = path.parent / ".snapshot-active.part"
    recent.write_bytes(b"tmp")
    cutoff = datetime.now(UTC) - timedelta(days=30)
    assert list(storage.expired_keys(cutoff)) == [key]
    assert storage.prune_temporary(cutoff) == 1
    assert recent.exists()


async def test_snapshot_codec_failure_still_publishes_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher = EventPublisher(cast(Redis, object()))
    writer = SnapshotWriter(LocalSnapshotStorage(tmp_path), publisher)
    frame = Frame(np.zeros((10, 10, 3), np.uint8), 1, 0, datetime.now(UTC))
    original = event()
    monkeypatch.setattr(cv2, "imencode", lambda *args: (False, None))
    writer.offer(original, frame, True)
    await writer.close()
    assert publisher.queue.get_nowait() is original


async def test_supervisor_drains_snapshots_before_stopping_delivery() -> None:
    from types import SimpleNamespace

    from vision_worker.supervisor import Supervisor

    order: list[str] = []
    main_stop, delivery_stop = asyncio.Event(), asyncio.Event()

    async def inference() -> None:
        await main_stop.wait()
        order.append("inference-stopped")

    async def close_snapshots() -> None:
        assert not delivery_stop.is_set()
        order.append("snapshots-drained")

    async def delivery() -> None:
        await delivery_stop.wait()
        assert order == ["inference-stopped", "snapshots-drained"]
        order.append("delivery-drained")

    async def cleanup() -> None:
        assert "delivery-drained" in order

    fake = SimpleNamespace(
        _stop=main_stop,
        _delivery_stop=delivery_stop,
        _tasks=[asyncio.create_task(inference())],
        _event_task=asyncio.create_task(delivery()),
        snapshots=SimpleNamespace(close=close_snapshots),
        _manager=SimpleNamespace(stop_all=cleanup),
        preview=SimpleNamespace(close=cleanup),
        telemetry=SimpleNamespace(close=cleanup),
        _camera_status=SimpleNamespace(publish_once=cleanup),
        _heartbeat=SimpleNamespace(withdraw=cleanup),
        _api_http=SimpleNamespace(aclose=cleanup),
        _redis=SimpleNamespace(aclose=cleanup),
    )
    await Supervisor.stop(cast(Supervisor, fake))
    assert order == ["inference-stopped", "snapshots-drained", "delivery-drained"]


def test_snapshot_key_uses_utc_calendar_day() -> None:
    from datetime import timezone

    camera, snapshot = uuid4(), uuid4()
    at = datetime(2026, 1, 2, 1, tzinfo=timezone(timedelta(hours=3)))
    assert snapshot_key(camera, at, snapshot) == f"snapshots/{camera}/2026/01/01/{snapshot}.jpg"
