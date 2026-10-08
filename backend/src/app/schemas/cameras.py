"""Camera API schemas. Source URLs are always masked in responses."""

import uuid
from typing import Annotated, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from ai_detector_core.cameras.source import (
    InvalidSourceError,
    SourceType,
    mask_source_url,
    validate_source_url,
)
from ai_detector_core.cameras.status import CameraRuntimeStatus, CameraStatus
from app.application.camera_service import CameraView

CameraName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CameraCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CameraName
    source_type: SourceType
    source_url: str = Field(max_length=2048)
    enabled: bool = False

    @model_validator(mode="after")
    def _check_source(self) -> Self:
        try:
            validate_source_url(self.source_type, self.source_url)
        except InvalidSourceError as exc:
            raise ValueError(str(exc)) from exc
        return self


class CameraUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CameraName | None = None
    source_type: SourceType | None = None
    source_url: str | None = Field(default=None, max_length=2048)


class CameraRuntimeRead(BaseModel):
    status: CameraStatus
    capture_fps: float
    frame_size: tuple[int, int] | None
    last_frame_at: AwareDatetime | None
    last_error: str | None
    reconnect_attempts: int
    last_reconnect_attempt_at: AwareDatetime | None
    worker_id: str
    updated_at: AwareDatetime

    @classmethod
    def from_status(cls, status: CameraRuntimeStatus) -> "CameraRuntimeRead":
        return cls(
            status=status.status,
            capture_fps=status.capture_fps,
            frame_size=status.frame_size,
            last_frame_at=status.last_frame_at,
            last_error=status.last_error,
            reconnect_attempts=status.reconnect_attempts,
            last_reconnect_attempt_at=status.last_reconnect_attempt_at,
            worker_id=status.worker_id,
            updated_at=status.updated_at,
        )


class CameraRead(BaseModel):
    id: uuid.UUID
    name: str
    source_type: SourceType
    source_url: str = Field(description="Credentials are masked")
    enabled: bool = Field(description="Desired state: the camera should be running")
    created_at: AwareDatetime
    updated_at: AwareDatetime
    runtime: CameraRuntimeRead | None = Field(
        description="Live status from the worker; null when no worker reports this camera"
    )

    @classmethod
    def from_view(cls, view: CameraView) -> "CameraRead":
        camera = view.camera
        return cls(
            id=camera.id,
            name=camera.name,
            source_type=SourceType(camera.source_type),
            source_url=mask_source_url(camera.source_url),
            enabled=camera.enabled,
            created_at=camera.created_at,
            updated_at=camera.updated_at,
            runtime=CameraRuntimeRead.from_status(view.runtime) if view.runtime else None,
        )
