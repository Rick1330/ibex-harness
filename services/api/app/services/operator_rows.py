"""Row access helpers shared by the operator read models."""

from __future__ import annotations

from typing import Any


def row_value(row: Any, key: str) -> Any:
    """Read a mapping key or an attribute, whichever the driver returned."""
    try:
        return row[key]
    except (KeyError, TypeError):
        return getattr(row, key)
