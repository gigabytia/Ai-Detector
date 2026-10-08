"""Readiness and system status: which dependencies and workers are available."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from ai_detector_core.ports.clock import Clock
from ai_detector_core.telemetry.heartbeat import WorkerHeartbeat

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_SECONDS = 2.0


class DependencyProbe(Protocol):
    name: str

    async def check(self) -> None:
        """Return normally when the dependency is usable, raise otherwise."""
        ...


class WorkerHeartbeatReader(Protocol):
    async def list_heartbeats(self) -> list[WorkerHeartbeat]: ...


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    ok: bool
    error: str | None


@dataclass(frozen=True)
class SystemStatus:
    dependencies: list[DependencyStatus]
    workers: list[WorkerHeartbeat]

    @property
    def ready(self) -> bool:
        return all(item.ok for item in self.dependencies)


class SystemService:
    def __init__(
        self,
        probes: list[DependencyProbe],
        heartbeats: WorkerHeartbeatReader,
        redis_probe_name: str,
        clock: Clock,
    ) -> None:
        self._probes = probes
        self._heartbeats = heartbeats
        self._redis_probe_name = redis_probe_name
        self._clock = clock

    @property
    def clock(self) -> Clock:
        return self._clock

    async def check_dependencies(self) -> list[DependencyStatus]:
        return list(await asyncio.gather(*(self._run_probe(probe) for probe in self._probes)))

    async def get_status(self) -> SystemStatus:
        dependencies = await self.check_dependencies()
        redis_ok = any(d.ok for d in dependencies if d.name == self._redis_probe_name)
        workers = await self._heartbeats.list_heartbeats() if redis_ok else []
        return SystemStatus(dependencies=dependencies, workers=workers)

    async def _run_probe(self, probe: DependencyProbe) -> DependencyStatus:
        try:
            async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
                await probe.check()
        except Exception as exc:
            logger.warning(
                "dependency check failed",
                extra={"dependency": probe.name, "error_type": type(exc).__name__},
                exc_info=exc,
            )
            return DependencyStatus(name=probe.name, ok=False, error=type(exc).__name__)
        return DependencyStatus(name=probe.name, ok=True, error=None)
