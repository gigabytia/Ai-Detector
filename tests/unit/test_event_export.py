"""CSV encoding and safety caps, independent of database/browser locale."""

import csv
import io
from datetime import UTC, datetime

import pytest

from app.application import event_export
from app.application.errors import UnprocessableError
from app.application.event_export import csv_cell, encode_export


@pytest.mark.parametrize(
    "value", ["=1+1", "+SUM(1)", "-1+2", "@SUM(1)", "  =1", "\t=2", "\rtest", "\ntext", "\ufeff =3"]
)
def test_formula_cells_are_prefixed_not_merely_csv_quoted(value: str) -> None:
    assert csv_cell(value) == "'" + value


def test_csv_roundtrip_cyrillic_quotes_newlines_null_and_utc() -> None:
    payload = encode_export(
        [
            {
                "message": 'Зона, "участок"\nёж',
                "note": "  =1+1",
                "occurred_at": datetime(2026, 1, 1, tzinfo=UTC),
                "metadata_json": {"zone": "Опасно"},
            }
        ]
    )
    assert payload.startswith(b"\xef\xbb\xbf") and b"\r\n" in payload
    row = next(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline="")))
    assert row["message"] == 'Зона, "участок"\nёж' and row["note"] == "'  =1+1"
    assert row["occurred_at"] == "2026-01-01T00:00:00Z" and row["snapshot_id"] == ""
    assert "Опасно" in row["metadata_json"]
    assert len(list(csv.reader(io.StringIO(encode_export([]).decode("utf-8-sig"))))) == 1


@pytest.mark.parametrize("cap", ["rows", "bytes"])
def test_caps_reject_whole_export_instead_of_silent_truncation(
    monkeypatch: pytest.MonkeyPatch, cap: str
) -> None:
    monkeypatch.setattr(event_export, "MAX_EXPORT_ROWS" if cap == "rows" else "MAX_EXPORT_BYTES", 1)
    with pytest.raises(UnprocessableError) as error:
        encode_export([{}, {}])
    assert error.value.code == "EXPORT_TOO_LARGE"
