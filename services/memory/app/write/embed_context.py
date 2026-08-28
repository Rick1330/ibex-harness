"""Org context for embedding calls during a write request."""

from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID

_write_org_id: ContextVar[UUID | None] = ContextVar("write_org_id", default=None)


def set_write_org_id(org_id: UUID) -> object:
    return _write_org_id.set(org_id)


def reset_write_org_id(token: object) -> None:
    _write_org_id.reset(token)


def get_write_org_id() -> UUID:
    org_id = _write_org_id.get()
    if org_id is None:
        msg = "write org_id context not set"
        raise RuntimeError(msg)
    return org_id
