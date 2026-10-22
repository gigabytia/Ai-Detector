"""Optional snapshot metadata belongs to transport, not the rule domain event."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from ai_detector_core.events.domain import DomainEvent
from ai_detector_core.storage.snapshots import snapshot_key, validate_key


class SnapshotMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    event_id: UUID
    storage_key: str = Field(max_length=200)
    content_type: Literal["image/jpeg"] = "image/jpeg"
    width: int = Field(ge=1, le=16384)
    height: int = Field(ge=1, le=16384)
    size_bytes: int = Field(ge=1, le=50 * 1024 * 1024)
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _key(self) -> "SnapshotMetadata":
        validate_key(self.storage_key)
        return self


class EventMessage(DomainEvent):
    snapshot: SnapshotMetadata | None = None

    @model_validator(mode="after")
    def _binding(self) -> "EventMessage":
        if self.snapshot is not None and (
            self.snapshot.event_id != self.id
            or self.snapshot.storage_key
            != snapshot_key(self.camera_id, self.occurred_at, self.snapshot.id)
        ):
            raise ValueError("Snapshot does not belong to this event/camera/time")
        return self
