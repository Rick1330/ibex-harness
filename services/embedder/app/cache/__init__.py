"""Content-hash embedding cache (G4.M4)."""

from __future__ import annotations

from app.cache.backend import CachingEmbeddingBackend
from app.cache.context import embed_org_id, reset_embed_org_id, set_embed_org_id

__all__ = [
    "CachingEmbeddingBackend",
    "embed_org_id",
    "reset_embed_org_id",
    "set_embed_org_id",
]
