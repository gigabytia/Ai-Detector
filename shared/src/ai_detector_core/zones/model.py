"""Validated normalized danger-zone shape shared by API and worker."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_detector_core.zones.geometry import validate_polygon


class NormalizedPoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class ZoneShape(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    points: tuple[NormalizedPoint, ...] = Field(min_length=3, max_length=64)
    enabled: bool = True

    @model_validator(mode="after")
    def _valid_polygon(self) -> Self:
        validate_polygon(tuple((p.x, p.y) for p in self.points))
        return self


class ZoneSpec(ZoneShape):
    id: UUID
    camera_id: UUID
