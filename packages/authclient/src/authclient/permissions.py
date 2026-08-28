"""Permission bits — must match packages/permissions (ADR-0009)."""

from __future__ import annotations

MEMORY_READ = 1 << 0
MEMORY_WRITE = 1 << 1


def has_permission(bitmap: int, required: int) -> bool:
    return bitmap & required == required
