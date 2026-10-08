"""CameraManager: keeps running sessions equal to the desired state. No pipeline logic here."""

import asyncio
import logging
import uuid
from collections.abc import Callable, Sequence
from typing import Protocol

from ai_detector_core.cameras.spec import CameraSpec
from ai_detector_core.cameras.status import CameraRuntimeStatus, CameraStatus

logger = logging.getLogger(__name__)


class Session(Protocol):
    spec: CameraSpec

    @property
    def state(self) -> CameraStatus: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def status(self) -> CameraRuntimeStatus: ...


class CameraManager:
    """Called only from the asyncio thread; blocking stops run in a worker thread."""

    def __init__(self, session_factory: Callable[[CameraSpec], Session]) -> None:
        self._factory = session_factory
        self._sessions: dict[uuid.UUID, Session] = {}

    @property
    def sessions(self) -> list[Session]:
        return list(self._sessions.values())

    async def reconcile(self, specs: Sequence[CameraSpec]) -> None:
        """Full sync with the list of enabled cameras assigned to this worker."""
        desired = {spec.id: spec for spec in specs if spec.enabled}
        for camera_id in [cid for cid in self._sessions if cid not in desired]:
            await self._stop(camera_id)
        for spec in desired.values():
            await self.apply(spec.id, spec)

    async def apply(self, camera_id: uuid.UUID, spec: CameraSpec | None) -> None:
        """Bring one camera to its desired state. spec=None means the camera was deleted."""
        current = self._sessions.get(camera_id)
        if spec is None or not spec.enabled:
            if current is not None:
                await self._stop(camera_id)
            return
        if current is not None:
            same_source = (current.spec.source_type, current.spec.source_url) == (
                spec.source_type,
                spec.source_url,
            )
            if same_source and current.state is not CameraStatus.ERROR:
                current.spec = spec  # e.g. renamed; no need to reopen the source
                return
            await self._stop(camera_id)
        self._start(spec)

    async def restart(self, camera_id: uuid.UUID, spec: CameraSpec | None) -> None:
        if camera_id in self._sessions:
            await self._stop(camera_id)
        if spec is not None and spec.enabled:
            self._start(spec)

    async def stop_all(self) -> None:
        for camera_id in list(self._sessions):
            await self._stop(camera_id)

    def _start(self, spec: CameraSpec) -> None:
        session = self._factory(spec)
        self._sessions[spec.id] = session
        session.start()

    async def _stop(self, camera_id: uuid.UUID) -> None:
        session = self._sessions.pop(camera_id)
        await asyncio.to_thread(session.stop)
