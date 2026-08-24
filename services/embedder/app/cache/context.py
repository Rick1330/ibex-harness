"""Request-scoped org for the cache decorator (ABC embed(texts) unchanged)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from uuid import UUID

embed_org_id: ContextVar[UUID | None] = ContextVar("embed_org_id", default=None)


def set_embed_org_id(org_id: UUID) -> Token[UUID | None]:
    return embed_org_id.set(org_id)


def reset_embed_org_id(token: Token[UUID | None]) -> None:
    embed_org_id.reset(token)
