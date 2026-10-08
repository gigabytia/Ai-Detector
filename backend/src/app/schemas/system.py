"""Health and system status responses."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel


class LivenessRead(BaseModel):
    status: Literal["alive"]


class DependencyStatusRead(BaseModel):
    name: str
    ok: bool
    error: str | None


class ReadinessRead(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: list[DependencyStatusRead]


class WorkerStatusRead(BaseModel):
    worker_id: str
    version: str
    started_at: AwareDatetime
    last_seen_at: AwareDatetime
    uptime_seconds: float


class SystemStatusRead(BaseModel):
    status: Literal["ok", "degraded"]
    checked_at: AwareDatetime
    dependencies: list[DependencyStatusRead]
    workers: list[WorkerStatusRead]
