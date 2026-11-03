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


class StaleLifecycleError(ConflictError):
    code = "STALE_LIFECYCLE_REVISION"

    def __init__(self, message: str = "Lifecycle revision is stale") -> None:
        super().__init__(message)


class StaleMemoryRevisionError(StaleLifecycleError):
    """A supersession/PII target changed; callers may reload candidates and retry."""

    code = "STALE_MEMORY_REVISION"


class MemoryOrganizationUnavailableError(ConflictError):
    """The organization was cancelled while a memory write was pending."""

    code = "ORG_UNAVAILABLE"

    def __init__(self, message: str = "Organization no longer accepts memory writes") -> None:
        super().__init__(message)


class ExternalServiceError(IBEXError):
    code = "UPSTREAM_ERROR"
    http_status = 503


class EmbeddingServiceError(ExternalServiceError):
    code = "EMBEDDING_FAILED"


class MemoryDatabaseError(ExternalServiceError):
    code = "DATABASE_UNAVAILABLE"


class MemoryNotFoundError(IBEXError):
    code = "NOT_FOUND"
    http_status = 404

    def __init__(self) -> None:
        super().__init__("Memory not found")
