"""JSON log formatter for the standard logging module."""

import logging
import sys
from datetime import UTC, datetime

import orjson

# Attributes of LogRecord that are not user-supplied `extra` fields.
# uvicorn adds `color_message` with ANSI codes; it duplicates `message`.
_RESERVED = frozenset(vars(logging.makeLogRecord({})).keys()) | {
    "message",
    "asctime",
    "color_message",
}


class JsonFormatter(logging.Formatter):
    """One JSON object per line: timestamp, level, logger, message, extra fields."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "service": self._service,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return orjson.dumps(payload, default=str).decode()


def configure_json_logging(service: str, level: str) -> None:
    """Replace root handlers with a single JSON stdout handler."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
