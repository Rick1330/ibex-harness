"""Cursor pagination helpers for management API list endpoints."""

from __future__ import annotations

import base64
import json
from typing import Any, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationMeta(BaseModel):
    has_more: bool
    next_cursor: str | None = None
    prev_cursor: str | None = None
    total_count: int | None = None


class CursorPage[T](BaseModel):
    data: list[T]
    pagination: PaginationMeta


def encode_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    pad = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + pad)
        data = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise ValueError("invalid cursor") from exc
    if not isinstance(data, dict):
        raise TypeError("invalid cursor")
    return data


def _encode_next_cursor(
    *,
    has_more: bool,
    page_rows: list[Any],
    cursor_payload: dict[str, Any] | None,
) -> str | None:
    if not has_more or not page_rows or cursor_payload is None:
        return None
    return encode_cursor(cursor_payload)


def page_from_rows[T](
    rows: list[T],
    *,
    limit: int,
    cursor_payload: dict[str, Any] | None,
    total_count: int | None = None,
) -> CursorPage[T]:
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    return CursorPage(
        data=page_rows,
        pagination=PaginationMeta(
            has_more=has_more,
            next_cursor=_encode_next_cursor(
                has_more=has_more,
                page_rows=page_rows,
                cursor_payload=cursor_payload,
            ),
            total_count=total_count,
        ),
    )


class ListQuery(BaseModel):
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=100)
