"""What the worker needs to run a camera. Served by the internal API (ADR-002)."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ai_detector_core.cameras.source import SourceType


class CameraSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    source_type: SourceType
    # Contains credentials for RTSP. Never log it; use mask_source_url().
    source_url: str
    enabled: bool
