"""Unit tests for the shared operator keyset cursor helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from apierror_py import VALIDATION_ERROR

from app.errors import ApiError
from app.pagination import decode_cursor, encode_cursor
from app.services.operator_keyset import (
    keyset_cursor_payload,
    parse_keyset_cursor,
)

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def test_absent_cursor_returns_empty_bounds() -> None:
    assert parse_keyset_cursor(None).created_at is None
    assert parse_keyset_cursor(None).row_id is None


def test_valid_cursor_round_trips() -> None:
    row_id = uuid4()
    cursor = encode_cursor(keyset_cursor_payload(NOW, row_id))

    parsed = parse_keyset_cursor(cursor)

    assert parsed.created_at == NOW
    assert parsed.row_id == row_id


@pytest.mark.parametrize(
    "cursor",
    [
        encode_cursor({"created_at": NOW.isoformat()}),
        encode_cursor({"id": str(uuid4())}),
        encode_cursor({"created_at": "not-a-time", "id": str(uuid4())}),
        encode_cursor({"created_at": "2026-11-02T12:00:00", "id": str(uuid4())}),
        encode_cursor({"created_at": NOW.isoformat(), "id": "not-a-uuid"}),
        "not+base64",
        "W10",
    ],
)
def test_malformed_cursors_are_rejected(cursor: str) -> None:
    with pytest.raises(ApiError) as exc:
        parse_keyset_cursor(cursor)
    assert exc.value.code == VALIDATION_ERROR


def test_payload_shape_is_stable() -> None:
    row_id = uuid4()
    assert keyset_cursor_payload(NOW, row_id) == {
        "created_at": NOW.isoformat(),
        "id": str(row_id),
    }
    assert decode_cursor(encode_cursor(keyset_cursor_payload(NOW, row_id))) == {
        "created_at": NOW.isoformat(),
        "id": str(row_id),
    }
