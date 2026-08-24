"""Typed embedding errors (fail-closed; mirror packages/embedder semantics)."""

from __future__ import annotations


class EmbedderError(Exception):
    """Base class for embedding contract violations."""

    code: str = "embedder_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnknownProfileError(EmbedderError):
    code = "unknown_profile"


class DuplicateProfileError(EmbedderError):
    code = "duplicate_profile"


class MissingBackendError(EmbedderError):
    code = "missing_backend"


class GeometryMismatchError(EmbedderError):
    code = "geometry_mismatch"


class EmptyBatchError(EmbedderError):
    code = "empty_batch"


class BatchTooLargeError(EmbedderError):
    code = "batch_too_large"


class TextTooLongError(EmbedderError):
    code = "text_too_long"


class InvalidVectorError(EmbedderError):
    code = "invalid_vector"


class ServiceNotReadyError(EmbedderError):
    code = "service_not_ready"
