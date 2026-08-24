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


class AuthenticationError(EmbedderError):
    code = "authentication_failed"


class BackendUnavailableError(EmbedderError):
    """TEI or upstream backend is unreachable or returned a server error.

    retryable is an internal client hint. Public error type stays the same for
    both transient (429/502/503/transport) and non-retryable (4xx/500) failures.
    retry_after_seconds is an optional client hint parsed from numeric Retry-After.
    """

    code = "backend_unavailable"

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class BackendTimeoutError(EmbedderError):
    """TEI request exceeded configured timeout."""

    code = "backend_timeout"


class BackendRejectedError(EmbedderError):
    """TEI rejected the request (413/422/424) — do not retry."""

    code = "backend_rejected"


class MissingOrgContextError(EmbedderError):
    """Cache enabled but request org_id ContextVar is unset."""

    code = "missing_org_context"
