"""SHA-256 content addressing and org-scoped Redis key format."""

from __future__ import annotations

import hashlib
import struct
from uuid import UUID

_KEY_PREFIX = "embed:v1"


def content_digest(*, model_id: str, dimensions: int, text: str) -> str:
    """Return hex SHA-256 of length-prefixed (model_id, dim, utf-8 text).

    Exact UTF-8 bytes only — no NFC/lowercase (must match inference input).
    Length prefixes avoid delimiter collisions with model ids containing ``|``.
    """
    model_bytes = model_id.encode("utf-8")
    text_bytes = text.encode("utf-8")
    payload = (
        struct.pack(">I", len(model_bytes))
        + model_bytes
        + struct.pack(">I", dimensions)
        + struct.pack(">I", len(text_bytes))
        + text_bytes
    )
    return hashlib.sha256(payload).hexdigest()


def redis_key(*, org_id: UUID, digest_hex: str) -> str:
    """Tenant-scoped cache key: ``{org_id}:embed:v1:{hex}``."""
    return f"{org_id}:{_KEY_PREFIX}:{digest_hex}"


def cache_key_for_text(
    *,
    org_id: UUID,
    model_id: str,
    dimensions: int,
    text: str,
) -> str:
    digest = content_digest(model_id=model_id, dimensions=dimensions, text=text)
    return redis_key(org_id=org_id, digest_hex=digest)
