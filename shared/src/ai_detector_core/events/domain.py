"""Generated domain event. Transport and persistence are separate concerns."""

from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

UnitFloat = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class ZoneEntryMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)
    bbox: tuple[UnitFloat, UnitFloat, UnitFloat, UnitFloat]
    anchor: tuple[UnitFloat, UnitFloat]
    dwell_seconds: float = Field(ge=0, allow_inf_nan=False)
    stability: UnitFloat


class LineCrossMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    bbox: tuple[UnitFloat, UnitFloat, UnitFloat, UnitFloat]
    anchor: tuple[UnitFloat, UnitFloat]
    stability: UnitFloat
    direction: Literal["LEFT_TO_RIGHT", "RIGHT_TO_LEFT"]
    line_name: str = Field(min_length=1, max_length=100)
    p1: tuple[UnitFloat, UnitFloat]
    p2: tuple[UnitFloat, UnitFloat]


class LoiteringMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    bbox: tuple[UnitFloat, UnitFloat, UnitFloat, UnitFloat]
    anchor: tuple[UnitFloat, UnitFloat]
    stability: UnitFloat
    zone_name: str = Field(min_length=1, max_length=100)
    duration_seconds: float = Field(gt=0, allow_inf_nan=False)
    threshold_seconds: float = Field(ge=0, le=3600, allow_inf_nan=False)

    @model_validator(mode="after")
    def _exceeded(self) -> Self:
        if self.duration_seconds <= self.threshold_seconds:
            raise ValueError("Loitering duration must exceed threshold")
        return self


class DomainEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID = Field(default_factory=uuid4)
    camera_id: UUID
    run_id: UUID
    track_id: int = Field(ge=1)
    zone_id: UUID | None = None
    line_id: UUID | None = None
    type: Literal[
        "PERSON_ENTERED_DANGER_ZONE", "PERSON_CROSSED_LINE", "PERSON_LOITERING_IN_DANGER_ZONE"
    ] = "PERSON_ENTERED_DANGER_ZONE"
    severity: Literal["critical", "warning", "info"] = "critical"
    occurred_at: AwareDatetime
    source_ts_ms: float = Field(ge=0, allow_inf_nan=False)
    detector_confidence: UnitFloat
    event_confidence: UnitFloat
    message: str
    metadata: ZoneEntryMetadata | LineCrossMetadata | LoiteringMetadata

    @model_validator(mode="after")
    def _typed_metadata(self) -> Self:
        if self.type == "PERSON_ENTERED_DANGER_ZONE":
            if (
                self.zone_id is None
                or self.line_id is not None
                or not isinstance(self.metadata, ZoneEntryMetadata)
            ):
                raise ValueError("Zone entry requires zone_id and zone metadata only")
        elif self.type == "PERSON_LOITERING_IN_DANGER_ZONE":
            if (
                self.zone_id is None
                or self.line_id is not None
                or not isinstance(self.metadata, LoiteringMetadata)
            ):
                raise ValueError("Loitering requires zone_id and loitering metadata only")
        elif (
            self.line_id is None
            or self.zone_id is not None
            or not isinstance(self.metadata, LineCrossMetadata)
        ):
            raise ValueError("Line crossing requires line_id and line metadata only")
        return self
