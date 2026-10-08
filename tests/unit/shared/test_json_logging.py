import json
import logging
import sys

from ai_detector_core.observability.json_logging import JsonFormatter


def test_formats_extra_fields_and_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        exc_info = sys.exc_info()
    record = logging.makeLogRecord(
        {
            "name": "x",
            "levelno": logging.ERROR,
            "levelname": "ERROR",
            "msg": "camera failed",
            "exc_info": exc_info,
            "camera_id": "c1",
        }
    )

    payload = json.loads(JsonFormatter(service="test").format(record))

    assert payload["message"] == "camera failed"
    assert payload["service"] == "test"
    assert payload["camera_id"] == "c1"
    assert "ValueError: boom" in payload["exception"]
