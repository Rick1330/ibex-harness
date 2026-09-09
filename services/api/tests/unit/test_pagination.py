"""Unit tests for cursor pagination helpers."""

from __future__ import annotations

import pytest

from app.pagination import decode_cursor, encode_cursor, page_from_rows


def test_encode_decode_round_trip() -> None:
    payload = {"created_at": "2026-01-01T00:00:00+00:00", "id": "abc"}
    cursor = encode_cursor(payload)
    assert decode_cursor(cursor) == payload


def test_decode_cursor_none() -> None:
    assert decode_cursor(None) is None
    assert decode_cursor("") is None


def test_decode_cursor_invalid() -> None:
    with pytest.raises(ValueError, match="invalid cursor"):
        decode_cursor("%%%")


def test_page_from_rows_has_more() -> None:
    rows = [1, 2, 3]
    page = page_from_rows(rows, limit=2, cursor_payload={"id": "2"})
    assert page.data == [1, 2]
    assert page.pagination.has_more is True
    assert page.pagination.next_cursor is not None


def test_page_from_rows_complete() -> None:
    page = page_from_rows([1], limit=2, cursor_payload={"id": "1"})
    assert page.pagination.has_more is False
    assert page.pagination.next_cursor is None
