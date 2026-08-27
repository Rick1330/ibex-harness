"""Normalize memory content and compute SHA-256 content_hash (m3.C.2)."""

from __future__ import annotations

import hashlib
import re

_WS = re.compile(r"\s+")


def normalize_content(content: str) -> str:
    """Whitespace-collapse and lowercase for exact-dedup hashing."""
    return _WS.sub(" ", content.strip()).lower()


def content_hash_sha256(content: str) -> str:
    """SHA-256 hex digest of normalized content (64 lowercase hex chars)."""
    normalized = normalize_content(content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
