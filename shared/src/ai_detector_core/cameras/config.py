"""Effective camera configuration. Defaults are owned by the API, not the worker."""

from pydantic import BaseModel, ConfigDict, Field


class CameraConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_fps: float = Field(default=10, ge=1, le=30)
    detection_confidence: float = Field(default=0.25, gt=0, le=1)
    zone_enter_dwell_seconds: float = Field(default=0.25, ge=0, le=3600)
    zone_exit_grace_seconds: float = Field(default=0.5, ge=0, le=3600)
    event_cooldown_seconds: float = Field(default=3, ge=0, le=3600)


class CameraConfigOverrides(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_fps: float | None = Field(default=None, ge=1, le=30)
    detection_confidence: float | None = Field(default=None, gt=0, le=1)
    zone_enter_dwell_seconds: float | None = Field(default=None, ge=0, le=3600)
    zone_exit_grace_seconds: float | None = Field(default=None, ge=0, le=3600)
    event_cooldown_seconds: float | None = Field(default=None, ge=0, le=3600)

    def resolve(self, defaults: CameraConfig) -> CameraConfig:
        return CameraConfig.model_validate(
            defaults.model_dump() | self.model_dump(exclude_none=True)
        )


class CameraConfigRead(BaseModel):
    overrides: CameraConfigOverrides
    defaults: CameraConfig
    effective: CameraConfig
