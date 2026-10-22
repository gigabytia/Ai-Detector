"""Finite normalized directed line, shared by API and worker."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_detector_core.zones.model import NormalizedPoint


class LineShape(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    p1: NormalizedPoint
    p2: NormalizedPoint
    enabled: bool = True

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        if (self.p1.x - self.p2.x) ** 2 + (self.p1.y - self.p2.y) ** 2 <= 1e-12:
            raise ValueError("Line endpoints must be distinct (distance > 1e-6)")
        return self


class LineSpec(LineShape):
    id: UUID
    camera_id: UUID
