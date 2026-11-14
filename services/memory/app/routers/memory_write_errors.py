"""Write-error classification and stable HTTP envelopes for memory writes.

The helpers here answer two questions about a failed write: *what* failed
(foreign-key constraint inspection, unknown-agent detection) and *how the
failure is reported* (the status/code/message envelope). Keeping the two
together leaves the write orchestration in ``memory_write_support`` free of
driver-specific error sniffing.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.exceptions import (
    DuplicateMemoryError,
    EmbeddingServiceError,
    MemoryOrganizationUnavailableError,
    StaleLifecycleError,
    ValidationError,
)

_UNKNOWN_AGENT_CONSTRAINT = "memories_agent_org_fk"
_FOREIGN_KEY_VIOLATION = "23503"
# The ledger's claim INSERT references ibex_core.agents(id) on its own, so a
# globally unknown agent id is the only thing that violates this constraint. An
# agent that exists in another organization passes it and is rejected later by
# the memories (agent_id, org_id) composite FK instead.
_LEDGER_AGENT_CONSTRAINT = "idempotency_ledger_agent_id_fkey"


def _http_error(
    status_code: int,
    code: str,
    message: str,
    **extra: object,
) -> HTTPException:
    """Build the stable ``{code, message}`` error envelope."""
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, **extra},
    )


def _is_foreign_key_violation(orig: object) -> bool:
    """True when the driver error carries the 23503 foreign-key sqlstate."""
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return sqlstate == _FOREIGN_KEY_VIOLATION


def _named_constraint(orig: object, exc: BaseException) -> str | None:
    """Name the constraint from the driver, falling back to the error text.

    asyncpg populates ``constraint_name``; the message fallback covers a driver
    that only puts it in the error text.
    """
    diag = getattr(orig, "diag", None)
    constraint = getattr(orig, "constraint_name", None) or (
        getattr(diag, "constraint_name", None) if diag is not None else None
    )
    if constraint:
        return str(constraint)
    message = f"{orig!s} {exc!s}"
    for name in (_UNKNOWN_AGENT_CONSTRAINT, _LEDGER_AGENT_CONSTRAINT):
        if name in message:
            return name
    return None


def foreign_key_constraint(exc: BaseException) -> str | None:
    """Name the constraint an ``IntegrityError`` violated, or ``None``.

    Returns ``None`` when the error is not a 23503 foreign-key violation, and
    when the driver reported neither a constraint name nor a message naming a
    known one.
    """
    if not isinstance(exc, IntegrityError):
        return None
    orig = getattr(exc, "orig", None)
    if orig is None or not _is_foreign_key_violation(orig):
        return None
    return _named_constraint(orig, exc)


def is_unknown_agent_violation(exc: BaseException) -> bool:
    """True when a memories insert failed the composite (agent_id, org_id) FK.

    ``memories_agent_org_fk`` is the only constraint that rejects an agent id
    absent from the caller's organization. Mapping it to a 404 keeps "unknown
    agent" from becoming a 500, and the same 404 covers an agent owned by
    another tenant, so the response does not leak existence across orgs.
    """
    return foreign_key_constraint(exc) == _UNKNOWN_AGENT_CONSTRAINT


def is_unknown_agent_ledger_rejection(exc: BaseException) -> bool:
    """True when the ledger refused a claim because the agent row is missing.

    ``PostgresIdempotencyLedger.claim`` raises ``LedgerValidationError`` for any
    foreign-key rejection of its INSERT, which references both
    ``ibex_core.organizations(id)`` and ``ibex_core.agents(id)``. Only the agent
    case has an unkeyed counterpart — an unknown agent is a 404 there — so a
    keyed request must answer 404 as well rather than turning the same condition
    into a 400. The organization case keeps its existing 400. The constraint the
    database named is the only thing that distinguishes them, and the ledger
    keeps the ``IntegrityError`` as the validation error's cause.
    """
    cause = exc.__cause__
    return cause is not None and foreign_key_constraint(cause) == _LEDGER_AGENT_CONSTRAINT


def http_error_for_unknown_agent() -> HTTPException:
    """404 for an agent id the caller's organization cannot resolve."""
    return _http_error(404, "NOT_FOUND", "Agent not found")


def http_error_for_write(exc: BaseException) -> HTTPException:
    """Map a domain write failure to its stable HTTP envelope."""
    if isinstance(exc, (MemoryOrganizationUnavailableError, StaleLifecycleError)):
        return _http_error(409, exc.code, exc.message)
    if isinstance(exc, DuplicateMemoryError):
        return _http_error(
            409,
            "DUPLICATE_CONTENT",
            "A memory with identical content already exists",
            existing_memory_id=str(exc.existing_id),
        )
    if isinstance(exc, ValidationError):
        return _http_error(400, exc.code, exc.message)
    if isinstance(exc, EmbeddingServiceError):
        return _http_error(503, "EMBEDDING_FAILED", "Embedding service unavailable")
    raise exc


def http_internal_error_for_write() -> HTTPException:
    return _http_error(500, "INTERNAL_ERROR", "Memory write failed")


def idempotency_unavailable_error() -> HTTPException:
    return _http_error(503, "IDEMPOTENCY_UNAVAILABLE", "Idempotency ledger unavailable")
