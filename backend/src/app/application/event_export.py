"""Complete bounded UTF-8 CSV; reject oversize, never silently truncate a report."""

import csv
import io
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from app.application.errors import UnprocessableError

MAX_EXPORT_ROWS = 50_000
MAX_EXPORT_BYTES = 20 * 1024 * 1024
EXPORT_COLUMNS = (
    "id",
    "occurred_at",
    "camera_id",
    "camera_name",
    "run_id",
    "track_id",
    "type",
    "severity",
    "status",
    "zone_id",
    "line_id",
    "detector_confidence",
    "event_confidence",
    "message",
    "note",
    "acknowledged_at",
    "false_positive_at",
    "metadata_json",
    "snapshot_id",
)


def export_too_large() -> UnprocessableError:
    error = UnprocessableError(
        "CSV exceeds 50000 rows or 20 MiB; narrow the period/camera/status/type filters"
    )
    error.code = "EXPORT_TOO_LARGE"
    return error


def csv_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    result = str(value).replace("\x00", "\ufffd")
    # Standard spreadsheet formula mitigation. CSV quoting alone is not sufficient.
    probe = result.lstrip().lstrip("\ufeff").lstrip()
    if result.startswith(("\t", "\r", "\n")) or probe.startswith(("=", "+", "-", "@")):
        return "'" + result
    return result


class CsvExportBuffer:
    """Incremental bounded output; callers need not materialize every database row."""

    def __init__(self) -> None:
        self.output = bytearray(b"\xef\xbb\xbf")
        self.line = io.StringIO(newline="")
        self.writer = csv.writer(self.line, lineterminator="\r\n")
        self.writer.writerow(EXPORT_COLUMNS)
        self.output.extend(self.line.getvalue().encode("utf-8"))
        self.rows = 0
        if len(self.output) > MAX_EXPORT_BYTES:
            raise export_too_large()

    def extend(self, rows: Iterable[Mapping[Any, Any]]) -> None:
        for row in rows:
            if self.rows >= MAX_EXPORT_ROWS:
                raise export_too_large()
            self.line.seek(0)
            self.line.truncate(0)
            self.writer.writerow([csv_cell(row.get(key)) for key in EXPORT_COLUMNS])
            data = self.line.getvalue().encode("utf-8")
            if len(self.output) + len(data) > MAX_EXPORT_BYTES:
                raise export_too_large()
            self.output.extend(data)
            self.rows += 1

    def finish(self) -> bytes:
        return bytes(self.output)


def encode_export(rows: Iterable[Mapping[Any, Any]]) -> bytes:
    buffer = CsvExportBuffer()
    buffer.extend(rows)
    return buffer.finish()
