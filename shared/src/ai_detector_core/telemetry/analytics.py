"""Versioned, bounded analytics transport; independent of critical alarms."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, model_validator

ANALYTICS_STREAM = "ad:analytics:ingest"
ANALYTICS_GROUP = "analytics-db"
ANALYTICS_DEAD = "ad:analytics:dead"


class Segment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    state: Literal["NORMAL", "LOST", "IN_DANGER_ZONE"]
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError("Segment end precedes start")
        return self


class AnalyticsBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: Literal[1] = 1
    id: UUID
    camera_id: UUID
    run_id: UUID


class CameraSample(AnalyticsBase):
    kind: Literal["sample"] = "sample"
    at: AwareDatetime
    persons: int = Field(ge=0, le=10000)
    persons_in_zone: int = Field(ge=0, le=10000)
    observed_seconds: float = Field(ge=0, le=3, allow_inf_nan=False)


class TrackSession(AnalyticsBase):
    kind: Literal["track"] = "track"
    track_id: int = Field(ge=1)
    started_at: AwareDatetime
    ended_at: AwareDatetime
    segments: tuple[Segment, ...] = Field(min_length=1, max_length=2048)
    truncated: bool = False

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.ended_at < self.started_at:
            raise ValueError("Session end precedes start")
        previous = self.started_at
        for segment in self.segments:
            if segment.start < previous or segment.end > self.ended_at:
                raise ValueError("Unordered or out-of-session segment")
            previous = segment.end
        return self


AnalyticsMessage = Annotated[CameraSample | TrackSession, Field(discriminator="kind")]
ANALYTICS_ADAPTER: TypeAdapter[AnalyticsMessage] = TypeAdapter(AnalyticsMessage)
