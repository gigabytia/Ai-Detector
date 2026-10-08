"""Logging setup for the API process."""

from ai_detector_core.observability.json_logging import configure_json_logging
from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    configure_json_logging(service="api", level=settings.log_level)
