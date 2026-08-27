"""Memory write-path deduplication (exact hash + near-dup via VectorStore)."""

from app.dedup.hash import content_hash_sha256, normalize_content
from app.dedup.service import DedupService
from app.dedup.types import DedupResult

__all__ = [
    "DedupResult",
    "DedupService",
    "content_hash_sha256",
    "normalize_content",
]
