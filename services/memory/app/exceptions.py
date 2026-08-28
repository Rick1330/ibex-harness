"""IBEX memory service exception hierarchy (CODING_STANDARDS.md)."""

from __future__ import annotations

from uuid import UUID


class IBEXError(Exception):
    """Base error with stable external code."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(IBEXError):
    code = "VALIDATION_ERROR"
    http_status = 400

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        field_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.field_code = field_code


class ConflictError(IBEXError):
    code = "CONFLICT"
    http_status = 409


class DuplicateMemoryError(ConflictError):
    code = "DUPLICATE_CONTENT"

    def __init__(self, existing_id: UUID) -> None:
        super().__init__("Memory with identical content exists")
        self.existing_id = existing_id


class ExternalServiceError(IBEXError):
    code = "UPSTREAM_ERROR"
    http_status = 503


class EmbeddingServiceError(ExternalServiceError):
    code = "EMBEDDING_FAILED"
