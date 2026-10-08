"""Runtime camera status published by the worker and read by the API."""

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class CameraStatus(StrEnum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class CameraRuntimeStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    camera_id: UUID
    run_id: UUID
    worker_id: str
    status: CameraStatus
    capture_fps: float = Field(ge=0)
    frame_size: tuple[int, int] | None
    last_frame_at: AwareDatetime | None
    last_error: str | None
    reconnect_attempts: int = Field(ge=0)
    last_reconnect_attempt_at: AwareDatetime | None
    updated_at: AwareDatetime
