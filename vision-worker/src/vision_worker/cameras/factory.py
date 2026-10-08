"""Builds a FrameSource and CameraSession for a spec. The only place that knows source types."""

from pathlib import Path

from ai_detector_core.cameras.source import SourceType, mock_scenario, upload_ref
from ai_detector_core.cameras.spec import CameraSpec
from ai_detector_core.ports.clock import Clock
from vision_worker.cameras.file_source import FileFrameSource
from vision_worker.cameras.mock_source import MockFrameSource
from vision_worker.cameras.reconnect import BackoffPolicy
from vision_worker.cameras.rtsp_source import RtspFrameSource
from vision_worker.cameras.session import CameraSession
from vision_worker.cameras.source import FrameSource


def build_source(spec: CameraSpec, upload_root: Path) -> FrameSource:
    match spec.source_type:
        case SourceType.FILE:
            return FileFrameSource(upload_root / upload_ref(spec.source_url))
        case SourceType.RTSP:
            return RtspFrameSource(spec.source_url)
        case SourceType.MOCK:
            return MockFrameSource(mock_scenario(spec.source_url))


class CameraSessionFactory:
    def __init__(
        self, upload_root: Path, backoff: BackoffPolicy, worker_id: str, clock: Clock
    ) -> None:
        self._upload_root = upload_root
        self._backoff = backoff
        self._worker_id = worker_id
        self._clock = clock

    def __call__(self, spec: CameraSpec) -> CameraSession:
        return CameraSession(
            spec=spec,
            source=build_source(spec, self._upload_root),
            backoff=self._backoff,
            worker_id=self._worker_id,
            clock=self._clock,
        )
