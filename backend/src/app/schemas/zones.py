"""Public zone DTOs, sharing geometry validation with the worker."""

from datetime import datetime

from ai_detector_core.zones.model import ZoneSpec


class ZoneRead(ZoneSpec):
    created_at: datetime
    updated_at: datetime
