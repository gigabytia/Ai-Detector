"""FrameSource: the only boundary between video input and the pipeline (§10)."""

from typing import Protocol

from vision_worker.cameras.frame import Frame


class SourceUnavailableError(Exception):
    """Temporary failure (network, camera reboot). The session reconnects with backoff."""


class SourceFatalError(Exception):
    """The source can never work as configured (missing file, unknown scenario)."""


class FrameSource(Protocol):
    """Blocking source, used from the camera's own capture thread."""

    def start(self) -> None:
        """Open the source. Raises SourceUnavailableError or SourceFatalError."""
        ...

    def read(self) -> Frame | None:
        """Block until the next frame. None means stop() was requested."""
        ...

    def stop(self) -> None:
        """Make a blocked read() return None. Final; thread-safe; releases nothing."""
        ...

    def close(self) -> None:
        """Release resources. Called only from the capture thread, after reads are done."""
        ...

    @property
    def label(self) -> str:
        """Source description that is safe to log (no credentials)."""
        ...
