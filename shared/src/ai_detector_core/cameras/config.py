"""Effective camera configuration. Defaults are owned by the API, not the worker."""

from pydantic import BaseModel, ConfigDict, Field


class CameraConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_fps: float = Field(default=10, ge=1, le=30)
    detection_confidence: float = Field(default=0.25, gt=0, le=1)


class CameraConfigOverrides(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_fps: float | None = Field(default=None, ge=1, le=30)
    detection_confidence: float | None = Field(default=None, gt=0, le=1)

    def resolve(self, defaults: CameraConfig) -> CameraConfig:
        return CameraConfig.model_validate(
            defaults.model_dump() | self.model_dump(exclude_none=True)
        )


class CameraConfigRead(BaseModel):
    overrides: CameraConfigOverrides
    defaults: CameraConfig
    effective: CameraConfig
