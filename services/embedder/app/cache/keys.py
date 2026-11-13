"""SHA-256 content addressing and org-scoped Redis key format."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from uuid import UUID

_KEY_PREFIX = "embed:v1"


@dataclass(frozen=True, slots=True)
class EmbeddingIdentity:
    """Everything that decides whether two cached vectors are interchangeable.

    A digest that omits any of these fields can address a vector another deployment
    produced: the same ``model_id`` at another Matryoshka dimension, or the same id
    serving different weights. The fields are enumerated once, here, so the digest
    and the key format cannot drift apart.
    """

    model_id: str
    dimensions: int
    model_revision: str | None = None


def content_digest(*, identity: EmbeddingIdentity, text: str) -> str:
    """Return hex SHA-256 of length-prefixed (model_id, dim, [revision], utf-8 text).

    Exact UTF-8 bytes only — no NFC/lowercase (must match inference input).
    Length prefixes avoid delimiter collisions with model ids containing ``|``.

    The revision is length-prefixed after ``dimensions`` and is hashed **only when
    it is non-empty**. ``None`` and ``""`` both mean "this deployment does not
    distinguish revisions", and that layout stays byte-identical to the
    pre-revision digest, so a deployment that never sets
    ``IBEX_EMBEDDING_MODEL_REVISION`` keeps every vector already in Redis. Configure
    a revision and every digest changes: existing entries become misses and are
    recomputed from the new weights, never served as if they came from them.
    """
    model_bytes = identity.model_id.encode("utf-8")
    text_bytes = text.encode("utf-8")
    parts = [
        struct.pack(">I", len(model_bytes)),
        model_bytes,
        struct.pack(">I", identity.dimensions),
    ]
    if identity.model_revision:
        revision_bytes = identity.model_revision.encode("utf-8")
        parts.append(struct.pack(">I", len(revision_bytes)))
        parts.append(revision_bytes)
    parts.append(struct.pack(">I", len(text_bytes)))
    parts.append(text_bytes)
    return hashlib.sha256(b"".join(parts)).hexdigest()


def redis_key(*, org_id: UUID, digest_hex: str) -> str:
    """Tenant-scoped cache key: ``{org_id}:embed:v1:{hex}``."""
    return f"{org_id}:{_KEY_PREFIX}:{digest_hex}"


def cache_key_for_text(*, org_id: UUID, identity: EmbeddingIdentity, text: str) -> str:
    """Tenant-scoped cache key for one text under one embedding identity."""
    return redis_key(
        org_id=org_id,
        digest_hex=content_digest(identity=identity, text=text),
    )
