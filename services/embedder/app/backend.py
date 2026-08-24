"""Backward-compat shim — import from app.backends.base directly."""

from app.backends.base import EmbeddingBackend

__all__ = ["EmbeddingBackend"]
