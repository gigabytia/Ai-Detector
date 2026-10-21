"""Generated domain event. Transport and persistence are separate concerns."""

from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

UnitFloat = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class ZoneEntryMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)
    bbox: tuple[UnitFloat, UnitFloat, UnitFloat, UnitFloat]
    anchor: tuple[UnitFloat, UnitFloat]
    dwell_seconds: float = Field(ge=0, allow_inf_nan=False)
    stability: UnitFloat


class DomainEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID = Field(default_factory=uuid4)
    camera_id: UUID
    run_id: UUID
    track_id: int = Field(ge=1)
    zone_id: UUID
    type: Literal["PERSON_ENTERED_DANGER_ZONE"] = "PERSON_ENTERED_DANGER_ZONE"
    severity: Literal["critical", "warning", "info"] = "critical"
    occurred_at: AwareDatetime
    source_ts_ms: float = Field(ge=0, allow_inf_nan=False)
    detector_confidence: UnitFloat
    event_confidence: UnitFloat
    message: str
    metadata: ZoneEntryMetadata
