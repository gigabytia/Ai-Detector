from itertools import pairwise
from pathlib import Path

import cv2
import numpy as np
import pytest

from vision_worker.cameras.file_source import FileFrameSource
from vision_worker.cameras.source import SourceFatalError

FPS = 50
FRAMES = 10


@pytest.fixture
def video(tmp_path: Path) -> Path:
    path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"MJPG"), FPS, (64, 48))
    assert writer.isOpened()
    for i in range(FRAMES):
        writer.write(np.full((48, 64, 3), i * 20, dtype=np.uint8))
    writer.release()
    return path


def test_file_source_loops_with_monotonic_time_and_discontinuity(video: Path) -> None:
    source = FileFrameSource(video)
    source.start()
    try:
        frames = [source.read() for _ in range(FRAMES * 2 + 2)]
    finally:
        source.close()
    assert all(f is not None for f in frames)
    real = [f for f in frames if f is not None]
    assert real[0].size == (64, 48)
    ids = [f.frame_id for f in real]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    stamps = [f.source_ts_ms for f in real]
    assert all(b > a for a, b in pairwise(stamps))
    # Played at real speed: 22 frames at 50 fps take ~0.42 s of source time.
    assert stamps[-1] - stamps[0] == pytest.approx((len(real) - 1) * 1000 / FPS, rel=0.2)
    jumps = [f.frame_id for f in real if f.discontinuity]
    assert jumps == [FRAMES + 1, 2 * FRAMES + 1]  # first frame of each new pass


def test_stop_unblocks_read(video: Path) -> None:
    source = FileFrameSource(video)
    source.start()
    assert source.read() is not None
    source.stop()
    assert source.read() is None
    source.close()


def test_missing_file_is_fatal(tmp_path: Path) -> None:
    with pytest.raises(SourceFatalError, match="not found"):
        FileFrameSource(tmp_path / "missing.mp4").start()


def test_garbage_file_is_fatal(tmp_path: Path) -> None:
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"not a video" * 100)
    source = FileFrameSource(path)
    with pytest.raises(SourceFatalError):
        source.start()
        source.read()
    source.close()
