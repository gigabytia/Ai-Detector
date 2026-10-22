"""Event REST and live schemas; no snapshots until M8."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

EventStatus = Literal["NEW", "ACKNOWLEDGED", "FALSE_POSITIVE"]


class EventRead(BaseModel):
    id: UUID
    camera_id: UUID
    run_id: UUID
    track_id: int
    zone_id: UUID | None
    type: Literal["PERSON_ENTERED_DANGER_ZONE"]
    severity: Literal["critical", "warning", "info"]
    status: EventStatus
    occurred_at: AwareDatetime
    source_ts_ms: float
    detector_confidence: float
    event_confidence: float
    message: str
    metadata: dict[str, object]
    note: str | None
    created_at: datetime
    updated_at: datetime
    acknowledged_at: datetime | None
    false_positive_at: datetime | None


class EventPage(BaseModel):
    items: list[EventRead]
    next_cursor: str | None


class EventUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ACKNOWLEDGED", "FALSE_POSITIVE"] | None = None
    note: str | None = Field(default=None, max_length=2000)
