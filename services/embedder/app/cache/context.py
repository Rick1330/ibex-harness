"""Request-scoped org for the cache decorator (ABC embed(texts) unchanged)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from uuid import UUID

embed_org_id: ContextVar[UUID | None] = ContextVar("embed_org_id", default=None)


def set_embed_org_id(org_id: UUID) -> Token[UUID | None]:
    return embed_org_id.set(org_id)


def reset_embed_org_id(token: Token[UUID | None]) -> None:
    embed_org_id.reset(token)


@contextmanager
def org_context(org_id: UUID) -> Iterator[UUID]:
    """Set embed_org_id for the duration of the block, then reset."""
    token = set_embed_org_id(org_id)
    try:
        yield org_id
    finally:
        reset_embed_org_id(token)
