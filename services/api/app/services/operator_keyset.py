"""Keyset cursor helpers shared by the operator read models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apierror_py import VALIDATION_ERROR

from app.errors import ApiError
from app.pagination import decode_cursor


@dataclass(frozen=True)
class KeysetCursor:
    created_at: datetime | None
    row_id: UUID | None


def parse_keyset_cursor(cursor: str | None) -> KeysetCursor:
    """Decode a ``(created_at, id)`` cursor and reject malformed or naive values."""
    try:
        payload = decode_cursor(cursor)
    except (TypeError, ValueError) as exc:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor") from exc
    if payload is None:
        return KeysetCursor(None, None)
    try:
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        row_id = UUID(str(payload["id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor") from exc
    if created_at.tzinfo is None:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor")
    return KeysetCursor(created_at, row_id)


def keyset_cursor_payload(created_at: datetime, row_id: UUID) -> dict[str, str]:
    return {"created_at": created_at.isoformat(), "id": str(row_id)}
