"""Public line DTOs, sharing endpoint validation with the worker."""

from datetime import datetime

from ai_detector_core.lines.model import LineSpec


class LineRead(LineSpec):
    created_at: datetime
    updated_at: datetime
