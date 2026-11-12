"""Canonical hashing of a published schema or description.

The hash is taken over the *title-free* canonical JSON form: Pydantic derives a
``title`` from a class or function name, so a rename would otherwise move the
hash without changing the contract. Only string-valued ``title`` keys go — a
property that happens to be *named* ``title`` keeps its own schema.
"""

from __future__ import annotations

import hashlib
import json
from typing import Final

SHORT_DIGEST_LENGTH: Final = 12


def canonical_sha256(value: object) -> str:
    """SHA-256 over the title-free canonical JSON form of a schema or description."""
    canonical = json.dumps(
        without_titles(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def short_digest(digest: object) -> str:
    """The first twelve hex characters of a hash, for a message a human can compare."""
    return str(digest)[:SHORT_DIGEST_LENGTH]


def without_titles(value: object) -> object:
    """Drop string-valued ``title`` keys at every depth; keep a *property* named title."""
    if isinstance(value, dict):
        kept = {key: item for key, item in value.items() if not _is_title(key, item)}
        return {key: without_titles(item) for key, item in kept.items()}
    if isinstance(value, list):
        return [without_titles(item) for item in value]
    return value


def _is_title(key: object, value: object) -> bool:
    return key == "title" and isinstance(value, str)
