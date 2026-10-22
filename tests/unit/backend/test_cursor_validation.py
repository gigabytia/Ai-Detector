"""Malformed untrusted cursors are client errors, never UUID type crashes."""

import base64
import json

import pytest

from app.application.errors import UnprocessableError
from app.application.event_service import decode_cursor


@pytest.mark.parametrize("event_id", [1, None, [], {}, True])
def test_nonstring_cursor_uuid_is_rejected(event_id: object) -> None:
    cursor = base64.urlsafe_b64encode(
        json.dumps(["2026-01-01T00:00:00+00:00", event_id]).encode()
    ).decode()
    with pytest.raises(UnprocessableError):
        decode_cursor(cursor)
